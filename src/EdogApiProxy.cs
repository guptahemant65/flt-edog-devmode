// <copyright file="EdogApiProxy.cs" company="Microsoft">
// Copyright (c) Microsoft Corporation. All rights reserved.
// </copyright>

#nullable disable
#pragma warning disable // DevMode-only file

namespace Microsoft.LiveTable.Service.DevMode
{
    using System;
    using System.IO;
    using System.Net.Http;
    using System.Text;
    using System.Text.Json;
    using System.Threading.Tasks;
    using Microsoft.AspNetCore.Http;

    /// <summary>
    /// Proxies FLT API calls from the EDOG log viewer to Fabric infrastructure.
    /// Reads config and token from edog.py's on-disk files.
    /// </summary>
    internal sealed class EdogApiProxy
    {
        private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(60) };
        private static readonly JsonSerializerOptions JsonOpts = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

        private readonly string configDir;

        public EdogApiProxy(string configDirectory)
        {
            this.configDir = configDirectory;
        }

        public async Task HandleConfig(HttpContext context)
        {
            context.Response.ContentType = "application/json";
            try
            {
                var config = await ReadConfig();
                if (config == null)
                {
                    await WriteError(context, 503, "config_not_found", "edog-config.json not found");
                    return;
                }

                var token = ReadToken();
                double expiryMinutes = 0;
                bool tokenExpired = true;

                if (token != null)
                {
                    expiryMinutes = Math.Max(0, Math.Floor((token.Value.ExpiryUtc - DateTime.UtcNow).TotalMinutes));
                    tokenExpired = false;
                }

                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    workspaceId = config.WorkspaceId,
                    artifactId = config.ArtifactId,
                    capacityId = config.CapacityId,
                    tokenExpiryMinutes = (int)expiryMinutes,
                    tokenExpired
                }, JsonOpts));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] HandleConfig error: {ex}");
                await WriteError(context, 500, "internal_error", ex.Message);
            }
        }

        public async Task HandleGetLatestDag(HttpContext context)
        {
            await ProxyFabricRequest(context, "HandleGetLatestDag", async (baseUrl, token) =>
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl}/liveTable/getLatestDag?showExtendedLineage=true");
                request.Headers.Add("Authorization", $"Bearer {token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());
                return await Http.SendAsync(request);
            });
        }

        public async Task HandleRunDag(HttpContext context)
        {
            await ProxyFabricRequest(context, "HandleRunDag", async (baseUrl, token) =>
            {
                var iterationId = Guid.NewGuid().ToString();

                using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/liveTableSchedule/runDAG/{iterationId}");
                request.Headers.Add("Authorization", $"Bearer {token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());

                var response = await Http.SendAsync(request);

                // Wrap RunDAG response with the generated iterationId
                context.Response.StatusCode = (int)response.StatusCode;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    iterationId,
                    statusCode = (int)response.StatusCode
                }, JsonOpts));
                return null; // Signal that response was already written
            });
        }

        public async Task HandleCancelDag(HttpContext context)
        {
            var iterationId = context.Request.RouteValues["iterationId"]?.ToString();
            if (string.IsNullOrEmpty(iterationId))
            {
                context.Response.ContentType = "application/json";
                await WriteError(context, 400, "missing_iteration_id", "iterationId is required");
                return;
            }

            await ProxyFabricRequest(context, "HandleCancelDag", async (baseUrl, token) =>
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/liveTableSchedule/cancelDAG/{iterationId}");
                request.Headers.Add("Authorization", $"Bearer {token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());
                return await Http.SendAsync(request);
            });
        }

        /// <summary>
        /// Shared proxy pipeline: validate config+token, execute the Fabric request, forward the response.
        /// When the callback returns null, the response has already been written (e.g., RunDAG's custom body).
        /// </summary>
        private async Task ProxyFabricRequest(
            HttpContext context,
            string handlerName,
            Func<string, string, Task<HttpResponseMessage>> executeRequest)
        {
            context.Response.ContentType = "application/json";
            try
            {
                var credentials = await ValidateAndGetCredentials(context);
                if (credentials == null) return; // Error response already written

                var (config, token) = credentials.Value;
                var baseUrl = BuildBaseUrl(config);

                var response = await executeRequest(baseUrl, token.Token);
                if (response == null) return; // Response already written by callback

                var body = await response.Content.ReadAsStringAsync();
                context.Response.StatusCode = (int)response.StatusCode;
                await context.Response.WriteAsync(body);
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"[EDOG] {handlerName} service error: {ex}");
                await WriteError(context, 502, "service_unreachable", ex.Message);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] {handlerName} error: {ex}");
                await WriteError(context, 500, "internal_error", ex.Message);
            }
        }

        /// <summary>
        /// Reads and validates config + token. Returns null and writes error response if either is missing.
        /// </summary>
        private async Task<(EdogConfig Config, TokenInfo Token)?> ValidateAndGetCredentials(HttpContext context)
        {
            var config = await ReadConfig();
            if (config == null)
            {
                await WriteError(context, 503, "config_not_found", "edog-config.json not found");
                return null;
            }

            var token = ReadToken();
            if (token == null)
            {
                await WriteError(context, 401, "token_expired", "Run edog --refresh-token in terminal");
                return null;
            }

            return (config, token.Value);
        }

        private static async Task WriteError(HttpContext context, int statusCode, string error, string message)
        {
            context.Response.StatusCode = statusCode;
            await context.Response.WriteAsync(JsonSerializer.Serialize(new { error, message }, JsonOpts));
        }

        private static string BuildBaseUrl(EdogConfig config)
        {
            return $"https://{config.CapacityId}.pbidedicated.windows-int.net/webapi/capacities/{config.CapacityId}/workloads/Lakehouse/LakehouseService/automatic/v1/workspaces/{config.WorkspaceId}/lakehouses/{config.ArtifactId}";
        }

        private async Task<EdogConfig> ReadConfig()
        {
            var path = Path.Combine(configDir, "edog-config.json");
            try
            {
                var json = await File.ReadAllTextAsync(path);
                var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;

                return new EdogConfig
                {
                    WorkspaceId = root.GetProperty("workspace_id").GetString(),
                    ArtifactId = root.GetProperty("artifact_id").GetString(),
                    CapacityId = root.GetProperty("capacity_id").GetString()
                };
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] Failed to read config: {ex.Message}");
                return null;
            }
        }

        private TokenInfo? ReadToken()
        {
            var path = Path.Combine(configDir, ".edog-token-cache");
            try
            {
                var raw = File.ReadAllText(path).Trim();
                var decoded = Encoding.UTF8.GetString(Convert.FromBase64String(raw));

                var separatorIndex = decoded.IndexOf('|');
                if (separatorIndex < 0)
                {
                    Console.WriteLine("[EDOG] Token cache has invalid format (no | separator)");
                    return null;
                }

                var expiryStr = decoded.Substring(0, separatorIndex);
                var token = decoded.Substring(separatorIndex + 1);

                if (!double.TryParse(expiryStr, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var expiryUnix))
                {
                    Console.WriteLine("[EDOG] Token cache has invalid expiry timestamp");
                    return null;
                }

                var expiryUtc = DateTimeOffset.FromUnixTimeSeconds((long)expiryUnix).UtcDateTime;
                var now = DateTime.UtcNow;

                // 5-minute buffer matching edog.py's logic
                if (now >= expiryUtc.AddSeconds(-300))
                {
                    Console.WriteLine("[EDOG] Token expired or expiring within 5 minutes");
                    return null;
                }

                return new TokenInfo { Token = token, ExpiryUtc = expiryUtc };
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] Failed to read token: {ex.Message}");
                return null;
            }
        }

        private class EdogConfig
        {
            public string WorkspaceId { get; set; }
            public string ArtifactId { get; set; }
            public string CapacityId { get; set; }
        }

        private struct TokenInfo
        {
            public string Token { get; set; }
            public DateTime ExpiryUtc { get; set; }
        }
    }
}

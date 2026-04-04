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
                    context.Response.StatusCode = 503;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "config_not_found",
                        message = "edog-config.json not found"
                    }, JsonOpts));
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

                var response = new
                {
                    workspaceId = config.WorkspaceId,
                    artifactId = config.ArtifactId,
                    capacityId = config.CapacityId,
                    tokenExpiryMinutes = (int)expiryMinutes,
                    tokenExpired
                };
                await context.Response.WriteAsync(JsonSerializer.Serialize(response, JsonOpts));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] HandleConfig error: {ex}");
                context.Response.StatusCode = 500;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "internal_error",
                    message = ex.Message
                }, JsonOpts));
            }
        }

        public async Task HandleGetLatestDag(HttpContext context)
        {
            context.Response.ContentType = "application/json";
            try
            {
                var config = await ReadConfig();
                var token = ReadToken();

                if (config == null)
                {
                    context.Response.StatusCode = 503;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "config_not_found",
                        message = "edog-config.json not found"
                    }, JsonOpts));
                    return;
                }

                if (token == null)
                {
                    context.Response.StatusCode = 401;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "token_expired",
                        message = "Run edog --refresh-token in terminal"
                    }, JsonOpts));
                    return;
                }

                var baseUrl = BuildBaseUrl(config);
                var request = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl}/liveTable/getLatestDag?showExtendedLineage=true");
                request.Headers.Add("Authorization", $"Bearer {token.Value.Token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());

                var response = await Http.SendAsync(request);
                var body = await response.Content.ReadAsStringAsync();

                context.Response.StatusCode = (int)response.StatusCode;
                await context.Response.WriteAsync(body);
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"[EDOG] HandleGetLatestDag service error: {ex}");
                context.Response.StatusCode = 502;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "service_unreachable",
                    message = ex.Message
                }, JsonOpts));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] HandleGetLatestDag error: {ex}");
                context.Response.StatusCode = 500;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "internal_error",
                    message = ex.Message
                }, JsonOpts));
            }
        }

        public async Task HandleRunDag(HttpContext context)
        {
            context.Response.ContentType = "application/json";
            try
            {
                var config = await ReadConfig();
                var token = ReadToken();

                if (config == null)
                {
                    context.Response.StatusCode = 503;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "config_not_found",
                        message = "edog-config.json not found"
                    }, JsonOpts));
                    return;
                }

                if (token == null)
                {
                    context.Response.StatusCode = 401;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "token_expired",
                        message = "Run edog --refresh-token in terminal"
                    }, JsonOpts));
                    return;
                }

                var baseUrl = BuildBaseUrl(config);
                var iterationId = Guid.NewGuid().ToString();

                var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/liveTableSchedule/runDAG/{iterationId}");
                request.Headers.Add("Authorization", $"Bearer {token.Value.Token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());

                var response = await Http.SendAsync(request);

                context.Response.StatusCode = (int)response.StatusCode;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    iterationId,
                    statusCode = (int)response.StatusCode
                }, JsonOpts));
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"[EDOG] HandleRunDag service error: {ex}");
                context.Response.StatusCode = 502;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "service_unreachable",
                    message = ex.Message
                }, JsonOpts));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] HandleRunDag error: {ex}");
                context.Response.StatusCode = 500;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "internal_error",
                    message = ex.Message
                }, JsonOpts));
            }
        }

        public async Task HandleCancelDag(HttpContext context)
        {
            context.Response.ContentType = "application/json";
            try
            {
                var iterationId = context.Request.RouteValues["iterationId"]?.ToString();
                if (string.IsNullOrEmpty(iterationId))
                {
                    context.Response.StatusCode = 400;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "missing_iteration_id",
                        message = "iterationId is required"
                    }, JsonOpts));
                    return;
                }

                var config = await ReadConfig();
                var token = ReadToken();

                if (config == null)
                {
                    context.Response.StatusCode = 503;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "config_not_found",
                        message = "edog-config.json not found"
                    }, JsonOpts));
                    return;
                }

                if (token == null)
                {
                    context.Response.StatusCode = 401;
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        error = "token_expired",
                        message = "Run edog --refresh-token in terminal"
                    }, JsonOpts));
                    return;
                }

                var baseUrl = BuildBaseUrl(config);
                var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/liveTableSchedule/cancelDAG/{iterationId}");
                request.Headers.Add("Authorization", $"Bearer {token.Value.Token}");
                request.Headers.Add("X-CORRELATION-ID", Guid.NewGuid().ToString());

                var response = await Http.SendAsync(request);
                var body = await response.Content.ReadAsStringAsync();

                context.Response.StatusCode = (int)response.StatusCode;
                await context.Response.WriteAsync(body);
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"[EDOG] HandleCancelDag service error: {ex}");
                context.Response.StatusCode = 502;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "service_unreachable",
                    message = ex.Message
                }, JsonOpts));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[EDOG] HandleCancelDag error: {ex}");
                context.Response.StatusCode = 500;
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    error = "internal_error",
                    message = ex.Message
                }, JsonOpts));
            }
        }

        private static string BuildBaseUrl(EdogConfig config)
        {
            return $"https://{config.CapacityId}.pbidedicated.windows-int.net/webapi/capacities/{config.CapacityId}/workloads/Lakehouse/LakehouseService/automatic/v1/workspaces/{config.WorkspaceId}/lakehouses/{config.ArtifactId}";
        }

        private async Task<EdogConfig> ReadConfig()
        {
            var path = Path.Combine(configDir, "edog-config.json");
            if (!File.Exists(path))
            {
                return null;
            }

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
            if (!File.Exists(path))
            {
                return null;
            }

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

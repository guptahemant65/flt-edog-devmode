// <copyright file="EdogLogInterceptor.cs" company="Microsoft">
// Copyright (c) Microsoft Corporation. All rights reserved.
// </copyright>

#nullable disable
#pragma warning disable // DevMode-only file — suppress all warnings

namespace Microsoft.LiveTable.Service.DevMode
{
    using System;
    using System.Collections.Concurrent;
    using System.Collections.Generic;
    using System.Linq;
    using System.Text.RegularExpressions;
    using System.Threading;
    using Microsoft.ServicePlatform.Telemetry;

    /// <summary>
    /// Intercepts Tracer.LogSanitized* calls and forwards FLT-relevant logs to EdogLogServer.
    ///
    /// Two-layer defence (filter at source + handle pressure on what survives):
    ///   Layer 1 — FLT allowlist: only FLT component patterns pass. Errors always pass.
    ///   Layer 2 — Error dedup: identical errors within a 2s window are collapsed so
    ///             relay-timeout-storms don't flood the pipeline.
    ///
    /// Pressure handling (truncation, dedup batching, adaptive flush, backpressure)
    /// lives in EdogLogServer.cs.
    /// </summary>
    internal sealed class EdogLogInterceptor : IStructuredTestLogger
    {
        private static readonly Regex IterationIdRegex = new Regex(
            @"(?:\[IterationId\s+|\bIterationId[=: ]+)([0-9a-fA-F-]{36})\b",
            RegexOptions.Compiled);

        // ── FLT component allowlist ──────────────────────────────────────
        // Mirrors the frontend COMPONENT_PRESETS.flt from edog-logs.html.
        // Allowlist > blocklist: new noisy platform components are excluded by default.
        private static readonly Regex[] FltComponentPatterns = new[]
        {
            new Regex(@"^LiveTable", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Workload\.LiveTable", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^LTWorkload", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^DqMetrics", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Insights", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^OneLake", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^DagExecution", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^DagCancellation", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^DagHook", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^NodeExecution", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Retry", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^StandardRetry", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Lineage", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^ExtendedLineage", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^FullLineage", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^RecursiveTraversal", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^ErrorMessage", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Cancellation$", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^GetConnected", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^GetDataQuality", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Cache$", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^sys_", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^DevMode$", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^WES$", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^Multischedule", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^IncludedLakehouses", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^SelectedOnly", RegexOptions.Compiled | RegexOptions.IgnoreCase),
            new Regex(@"^OC\.", RegexOptions.Compiled | RegexOptions.IgnoreCase),
        };

        // ── Error dedup — prevents relay-timeout-storm floods ────────────
        private const int ErrorDedupWindowMs = 2000;
        private const int ErrorMessageKeyLength = 120;
        private readonly ConcurrentDictionary<string, long> recentErrors = new();

        private readonly EdogLogServer edogLogServer;

        /// <summary>
        /// Initializes a new instance of the <see cref="EdogLogInterceptor"/> class.
        /// </summary>
        /// <param name="server">The EdogLogServer instance to forward logs to.</param>
        public EdogLogInterceptor(EdogLogServer server)
        {
            this.edogLogServer = server ?? throw new ArgumentNullException(nameof(server));
        }

        /// <summary>
        /// Intercepts trace events from the telemetry system. Only FLT-relevant logs
        /// and errors pass through. Everything else is dropped at the source.
        /// </summary>
        /// <param name="testLogEvent">The test log event containing telemetry data.</param>
        public void TraceEvent(TestLogEvent testLogEvent)
        {
            try
            {
                if (testLogEvent?.Message == null)
                {
                    return;
                }

                // Extract core data
                var timestamp = DateTime.UtcNow;
                var level = NormalizeLevel(testLogEvent.Level.ToString());
                var message = testLogEvent.Message;
                var component = ExtractComponent(MonitoredScope.CurrentCodeMarkerName, message);
                var rootActivityId = MonitoredScope.RootActivityId.ToString();
                var eventId = testLogEvent.EventId;

                var isError = level.Equals("Error", StringComparison.OrdinalIgnoreCase)
                           || level.Equals("Warning", StringComparison.OrdinalIgnoreCase);
                var isFltComponent = IsFltComponent(component);

                // ── Layer 1: Allowlist — drop non-FLT, non-error logs ───
                if (!isFltComponent && !isError)
                {
                    return;
                }

                // ── Layer 2: Error dedup — suppress duplicate error storms ─
                if (isError && !isFltComponent)
                {
                    var key = message.Length > ErrorMessageKeyLength
                        ? message.Substring(0, ErrorMessageKeyLength)
                        : message;
                    var nowTicks = Environment.TickCount64;

                    if (recentErrors.TryGetValue(key, out var lastTick) &&
                        (nowTicks - lastTick) < ErrorDedupWindowMs)
                    {
                        return;
                    }

                    recentErrors[key] = nowTicks;

                    if (recentErrors.Count > 200)
                    {
                        PruneRecentErrors(nowTicks);
                    }
                }

                // Parse custom data into dictionary
                var customData = new Dictionary<string, string>();
                if (testLogEvent.CustomData != null)
                {
                    foreach (var kvp in testLogEvent.CustomData)
                    {
                        customData[kvp.Key] = kvp.Value?.ToString() ?? string.Empty;
                    }
                }

                // Create log entry and forward to server
                var entry = new LogEntry(timestamp, level, message, component, rootActivityId, eventId, customData);
                entry.CodeMarkerName = MonitoredScope.CurrentCodeMarkerName;

                var iterMatch = IterationIdRegex.Match(message);
                if (iterMatch.Success)
                {
                    entry.IterationId = iterMatch.Groups[1].Value;
                }

                this.edogLogServer.AddLog(entry);

                // Console also filtered — no point printing noise to stdout
                this.WriteColoredConsoleOutput(level, component, rootActivityId, message);
            }
            catch
            {
                // Never throw from telemetry interceptor - silently handle any errors
            }
        }

        /// <summary>
        /// Returns true if the component matches FLT allowlist patterns.
        /// </summary>
        private static bool IsFltComponent(string component)
        {
            if (string.IsNullOrEmpty(component) || component == "Unknown")
            {
                return false;
            }

            for (int i = 0; i < FltComponentPatterns.Length; i++)
            {
                if (FltComponentPatterns[i].IsMatch(component))
                {
                    return true;
                }
            }

            return false;
        }

        private void PruneRecentErrors(long nowTicks)
        {
            foreach (var kvp in recentErrors)
            {
                if (nowTicks - kvp.Value > ErrorDedupWindowMs * 5)
                {
                    recentErrors.TryRemove(kvp.Key, out _);
                }
            }
        }

        /// <summary>
        /// Writes colored console output based on log level for developer visibility.
        /// </summary>
        private void WriteColoredConsoleOutput(string level, string component, string rootActivityId, string message)
        {
            try
            {
                var timestamp = DateTime.UtcNow.ToString("yyyy'-'MM'-'dd'T'HH':'mm':'ss.fffffffK");
                var formattedMessage = $"{timestamp} {level}: {component} : {rootActivityId} {message}";

                var originalColor = Console.ForegroundColor;
                
                Console.ForegroundColor = level.ToUpperInvariant() switch
                {
                    "MESSAGE" => ConsoleColor.Cyan,
                    "WARNING" => ConsoleColor.Yellow,
                    "ERROR" => ConsoleColor.Red,
                    "VERBOSE" => ConsoleColor.Gray,
                    _ => ConsoleColor.White
                };

                Console.WriteLine(formattedMessage);
                Console.ForegroundColor = originalColor;
            }
            catch
            {
                // Ignore console output errors - don't break logging pipeline
            }
        }

        /// <summary>
        /// Normalizes ServicePlatform TraceLevel enum names to the display names used by the frontend.
        /// The platform uses "Informational" but the UI expects "Message".
        /// </summary>
        private static string NormalizeLevel(string level)
        {
            return level switch
            {
                "Informational" => "Message",
                "Info" => "Message",
                _ => level
            };
        }

        /// <summary>
        /// Extracts a clean component name from the MonitoredScope code marker name.
        /// Strips WCL- prefixes and extracts FLT-specific bracket tags from messages.
        /// </summary>
        private static string ExtractComponent(string codeMarkerName, string message)
        {
            // Try to extract [BracketedComponent] from message first — most informative
            if (!string.IsNullOrEmpty(message))
            {
                int start = message.IndexOf('[');
                int end = message.IndexOf(']');
                if (start == 0 && end > 1 && end < 60)
                {
                    return message.Substring(1, end - 1);
                }
            }

            if (string.IsNullOrEmpty(codeMarkerName) || codeMarkerName == "Unknown")
            {
                return "Unknown";
            }

            // Clean up WCL- prefix and take meaningful suffix
            if (codeMarkerName.StartsWith("WCL-"))
            {
                return codeMarkerName.Substring(4);
            }

            return codeMarkerName;
        }
    }
}
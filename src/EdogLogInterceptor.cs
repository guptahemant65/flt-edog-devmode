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
    using Microsoft.ServicePlatform.Telemetry;
    /// <summary>
    /// Intercepts all Tracer.LogSanitized* calls and forwards them to EdogLogServer for dev-time analysis.
    /// Also writes colored console output so developers see logs in their terminal.
    /// </summary>
    internal sealed class EdogLogInterceptor : IStructuredTestLogger
    {
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
        /// Intercepts trace events from the telemetry system and forwards them to EdogLogServer.
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
                var level = testLogEvent.Level.ToString();
                var message = testLogEvent.Message;
                var component = MonitoredScope.CurrentCodeMarkerName ?? "Unknown";
                var rootActivityId = MonitoredScope.RootActivityId.ToString();
                var eventId = testLogEvent.EventId;

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
                this.edogLogServer.AddLog(entry);

                // Write colored console output for developer visibility
                this.WriteColoredConsoleOutput(level, component, rootActivityId, message);
            }
            catch
            {
                // Never throw from telemetry interceptor - silently handle any errors
            }
        }

        /// <summary>
        /// Writes colored console output based on log level for developer visibility.
        /// </summary>
        /// <param name="level">The log level.</param>
        /// <param name="component">The component name.</param>
        /// <param name="rootActivityId">The root activity ID.</param>
        /// <param name="message">The log message.</param>
        private void WriteColoredConsoleOutput(string level, string component, string rootActivityId, string message)
        {
            try
            {
                var timestamp = DateTime.UtcNow.ToString("yyyy'-'MM'-'dd'T'HH':'mm':'ss.fffffffK");
                var formattedMessage = $"{timestamp} {level}: {component} : {rootActivityId} {message}";

                var originalColor = Console.ForegroundColor;
                
                // Set color based on log level
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
    }
}
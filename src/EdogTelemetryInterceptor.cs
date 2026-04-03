// <copyright file="EdogTelemetryInterceptor.cs" company="Microsoft">
// Copyright (c) Microsoft Corporation. All rights reserved.
// </copyright>

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.LiveTable.Service.Telemetry;
using Microsoft.ServicePlatform.Telemetry;

namespace Microsoft.LiveTable.Service.DevMode
{
    /// <summary>
    /// Decorator that intercepts ICustomLiveTableTelemetryReporter calls and forwards them to EdogLogServer
    /// for dev-time analysis while maintaining the original telemetry flow.
    /// </summary>
    internal sealed class EdogTelemetryInterceptor : ICustomLiveTableTelemetryReporter
    {
        private readonly ICustomLiveTableTelemetryReporter inner;
        private readonly EdogLogServer edogLogServer;

        /// <summary>
        /// Initializes a new instance of the <see cref="EdogTelemetryInterceptor"/> class.
        /// </summary>
        /// <param name="inner">The inner telemetry reporter to forward calls to.</param>
        /// <param name="server">The EdogLogServer instance to forward telemetry events to.</param>
        public EdogTelemetryInterceptor(ICustomLiveTableTelemetryReporter inner, EdogLogServer server)
        {
            this.inner = inner ?? throw new ArgumentNullException(nameof(inner));
            this.edogLogServer = server ?? throw new ArgumentNullException(nameof(server));
        }

        /// <summary>
        /// Intercepts SSR telemetry events, forwards them to EdogLogServer, then passes them to the inner reporter.
        /// </summary>
        /// <param name="operationStartTime">The operation start time.</param>
        /// <param name="executingUserObjectId">The executing user object ID.</param>
        /// <param name="activityName">The activity name.</param>
        /// <param name="activityStatus">The activity status.</param>
        /// <param name="durationMs">The duration in milliseconds.</param>
        /// <param name="activityAttributes">Optional activity attributes.</param>
        /// <param name="correlationId">Optional correlation ID.</param>
        /// <param name="resultCode">Optional result code.</param>
        public void EmitStandardizedServerReporting(
            DateTime operationStartTime,
            Guid executingUserObjectId,
            string activityName,
            string activityStatus,
            long durationMs,
            IReadOnlyDictionary<string, string> activityAttributes = null,
            string correlationId = null,
            string resultCode = null)
        {
            try
            {
                // Create telemetry event for EdogLogServer
                var attributes = new Dictionary<string, string>();
                if (activityAttributes != null)
                {
                    foreach (var kvp in activityAttributes)
                    {
                        attributes[kvp.Key] = kvp.Value;
                    }
                }

                var telemetryEvent = new TelemetryEvent(
                    Timestamp: operationStartTime,
                    ActivityName: activityName ?? string.Empty,
                    ActivityStatus: activityStatus ?? string.Empty,
                    DurationMs: durationMs,
                    ResultCode: resultCode,
                    CorrelationId: string.IsNullOrEmpty(correlationId)
                        ? MonitoredScope.RootActivityId.ToString()
                        : correlationId,
                    Attributes: attributes,
                    UserId: executingUserObjectId.ToString());

                // Forward to EdogLogServer
                this.edogLogServer.AddTelemetry(telemetryEvent);

                // Write colored console output for developer visibility
                this.WriteColoredConsoleOutput(activityName, activityStatus, durationMs);
            }
            catch
            {
                // Never throw from telemetry interception - continue with original flow
            }

            try
            {
                // Always forward to the inner reporter to maintain original telemetry flow
                this.inner.EmitStandardizedServerReporting(
                    operationStartTime,
                    executingUserObjectId,
                    activityName,
                    activityStatus,
                    durationMs,
                    activityAttributes,
                    correlationId,
                    resultCode);
            }
            catch
            {
                // Don't suppress exceptions from the inner reporter as they may be important
                throw;
            }
        }

        /// <summary>
        /// Writes colored console output for telemetry events to provide developer visibility.
        /// </summary>
        /// <param name="activityName">The activity name.</param>
        /// <param name="activityStatus">The activity status.</param>
        /// <param name="durationMs">The duration in milliseconds.</param>
        private void WriteColoredConsoleOutput(string activityName, string activityStatus, long durationMs)
        {
            try
            {
                var message = $"[TELEMETRY] Activity: {activityName ?? "Unknown"} | Status: {activityStatus ?? "Unknown"} | Duration: {durationMs}ms";
                
                var originalColor = Console.ForegroundColor;
                Console.ForegroundColor = ConsoleColor.Magenta;
                Console.WriteLine(message);
                Console.ForegroundColor = originalColor;
            }
            catch
            {
                // Ignore console output errors - don't break telemetry pipeline
            }
        }
    }
}
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Timers;
using Community.VisualStudio.Toolkit;
using Microsoft.VisualStudio;
using Microsoft.VisualStudio.Shell;
using Microsoft.VisualStudio.Shell.Interop;
using Task = System.Threading.Tasks.Task;

namespace FLTEdogDevMode
{
    [PackageRegistration(UseManagedResourcesOnly = true, AllowsBackgroundLoading = true)]
    [Guid(PackageGuids.PackageGuidString)]
    [ProvideMenuResource("Menus.ctmenu", 1)]
    [ProvideAutoLoad(VSConstants.UICONTEXT.SolutionExistsAndFullyLoaded_string, PackageAutoLoadFlags.BackgroundLoad)]
    public sealed class FLTEdogDevModePackage : ToolkitPackage
    {
        public static FLTEdogDevModePackage Instance { get; private set; }
        
        private Process _pythonProcess;
        private DateTime? _tokenExpiry;
        private System.Timers.Timer _statusTimer;
        private IVsStatusbar _statusBar;
        
        public bool IsRunning => _pythonProcess != null && !_pythonProcess.HasExited;
        public DateTime? TokenExpiry => _tokenExpiry;

        protected override async Task InitializeAsync(CancellationToken cancellationToken, IProgress<ServiceProgressData> progress)
        {
            Instance = this;
            await base.InitializeAsync(cancellationToken, progress);
            
            await JoinableTaskFactory.SwitchToMainThreadAsync(cancellationToken);
            
            _statusBar = await GetServiceAsync(typeof(SVsStatusbar)) as IVsStatusbar;
            
            // Register commands
            await StartCommand.InitializeAsync(this);
            await StopCommand.InitializeAsync(this);
            await RevertCommand.InitializeAsync(this);
            await RefreshCommand.InitializeAsync(this);
            await StatusCommand.InitializeAsync(this);
            
            // Start status bar timer
            _statusTimer = new System.Timers.Timer(60000); // Update every minute
            _statusTimer.Elapsed += OnStatusTimerElapsed;
            _statusTimer.Start();
            
            UpdateStatusBar("FLT EDOG: Ready");
        }

        private void OnStatusTimerElapsed(object sender, ElapsedEventArgs e)
        {
            UpdateStatusBarWithExpiry();
        }

        public void UpdateStatusBar(string text)
        {
            ThreadHelper.JoinableTaskFactory.Run(async () =>
            {
                await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync();
                if (_statusBar != null)
                {
                    _statusBar.SetText($"🛡️ {text}");
                }
            });
        }

        public void UpdateStatusBarWithExpiry()
        {
            if (!IsRunning || !_tokenExpiry.HasValue)
            {
                UpdateStatusBar(IsRunning ? "FLT EDOG: Active" : "FLT EDOG: Ready");
                return;
            }

            var remaining = (int)(_tokenExpiry.Value - DateTime.Now).TotalMinutes;
            if (remaining <= 0)
            {
                UpdateStatusBar("FLT EDOG: Expired ⚠️");
            }
            else if (remaining <= 10)
            {
                UpdateStatusBar($"FLT EDOG: {remaining}m ⚠️");
            }
            else
            {
                UpdateStatusBar($"FLT EDOG: {remaining}m");
            }
        }

        public async Task<string> GetRepoRootAsync()
        {
            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync();
            var solution = await VS.Solutions.GetCurrentSolutionAsync();
            if (solution != null && !string.IsNullOrEmpty(solution.FullPath))
            {
                return Path.GetDirectoryName(solution.FullPath);
            }
            return null;
        }

        public async Task<string> GetPythonScriptPathAsync()
        {
            var repoRoot = await GetRepoRootAsync();
            if (string.IsNullOrEmpty(repoRoot)) return null;
            
            var scriptPath = Path.Combine(repoRoot, "get-edog-token.py");
            return File.Exists(scriptPath) ? scriptPath : null;
        }

        public async Task StartDevModeAsync()
        {
            if (IsRunning)
            {
                await VS.MessageBox.ShowAsync("FLT EDOG DevMode is already running");
                return;
            }

            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync();
            
            var scriptPath = await GetPythonScriptPathAsync();
            if (string.IsNullOrEmpty(scriptPath))
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", "Could not find get-edog-token.py in solution root");
                return;
            }

            UpdateStatusBar("FLT EDOG: Starting...");

            var repoRoot = await GetRepoRootAsync();
            var startInfo = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{scriptPath}\"",
                WorkingDirectory = repoRoot,
                UseShellExecute = true,  // Required for Playwright browser to launch properly
                CreateNoWindow = false   // Show window so browser can interact
            };

            _pythonProcess = new Process { StartInfo = startInfo };
            _pythonProcess.Exited += OnProcessExited;
            _pythonProcess.EnableRaisingEvents = true;

            try
            {
                _pythonProcess.Start();
                
                await VS.MessageBox.ShowAsync("FLT EDOG", "DevMode started. Token will be fetched via browser.");
            }
            catch (Exception ex)
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", $"Failed to start: {ex.Message}");
                _pythonProcess = null;
            }
        }

        private void OnProcessExited(object sender, EventArgs e)
        {
            _pythonProcess = null;
            UpdateStatusBar("FLT EDOG: Stopped");
        }

        public async Task StopDevModeAsync()
        {
            if (!IsRunning)
            {
                await VS.MessageBox.ShowAsync("FLT EDOG DevMode is not running");
                return;
            }

            try
            {
                _pythonProcess.Kill();
            }
            catch { }
            
            _pythonProcess = null;
            _tokenExpiry = null;
            UpdateStatusBar("FLT EDOG: Stopped");
            
            await VS.MessageBox.ShowAsync("FLT EDOG", "DevMode stopped. Run 'FLT EDOG: Revert' to undo changes.");
        }

        public async Task RevertChangesAsync()
        {
            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync();
            
            var scriptPath = await GetPythonScriptPathAsync();
            if (string.IsNullOrEmpty(scriptPath))
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", "Could not find get-edog-token.py");
                return;
            }

            UpdateStatusBar("FLT EDOG: Reverting...");

            var repoRoot = await GetRepoRootAsync();
            var startInfo = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{scriptPath}\" --revert",
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                CreateNoWindow = true
            };

            var process = Process.Start(startInfo);
            process.WaitForExit();

            if (process.ExitCode == 0)
            {
                await VS.MessageBox.ShowAsync("FLT EDOG", "All changes reverted successfully!");
                UpdateStatusBar("FLT EDOG: Ready");
            }
            else
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", "Failed to revert some changes");
            }
        }

        public async Task ShowStatusAsync()
        {
            await ThreadHelper.JoinableTaskFactory.SwitchToMainThreadAsync();
            
            var scriptPath = await GetPythonScriptPathAsync();
            if (string.IsNullOrEmpty(scriptPath))
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", "Could not find get-edog-token.py");
                return;
            }

            var repoRoot = await GetRepoRootAsync();
            var startInfo = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = $"\"{scriptPath}\" --status",
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            try
            {
                var process = Process.Start(startInfo);
                var output = await process.StandardOutput.ReadToEndAsync();
                var error = await process.StandardError.ReadToEndAsync();
                process.WaitForExit();

                var status = $"Running: {(IsRunning ? "Yes" : "No")}\n";
                if (_tokenExpiry.HasValue)
                {
                    var remaining = (int)(_tokenExpiry.Value - DateTime.Now).TotalMinutes;
                    status += $"Token Expires: {_tokenExpiry.Value:HH:mm:ss} ({remaining}m remaining)\n";
                }
                
                if (!string.IsNullOrEmpty(output))
                {
                    status += "\nCode Changes:\n" + output;
                }
                if (!string.IsNullOrEmpty(error))
                {
                    status += "\nErrors:\n" + error;
                }

                await VS.MessageBox.ShowAsync("FLT EDOG Status", status);
            }
            catch (Exception ex)
            {
                await VS.MessageBox.ShowErrorAsync("FLT EDOG", $"Failed to get status: {ex.Message}");
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _statusTimer?.Stop();
                _statusTimer?.Dispose();
                
                if (IsRunning)
                {
                    try { _pythonProcess.Kill(); } catch { }
                }
            }
            base.Dispose(disposing);
        }
    }
}

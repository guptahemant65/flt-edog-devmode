import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';

// State
let statusBarItem: vscode.StatusBarItem;
let pythonProcess: ChildProcess | null = null;
let currentToken: string | null = null;
let tokenExpiry: Date | null = null;
let isRunning = false;
let checkInterval: NodeJS.Timeout | null = null;

// Constants
const PYTHON_SCRIPT = 'get-edog-token.py';

export function activate(context: vscode.ExtensionContext) {
    console.log('FLT EDOG DevMode extension activated');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'flt-edog.status';
    updateStatusBar('$(shield) FLT EDOG: Ready', 'Click to see status');
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('flt-edog.start', startDevMode),
        vscode.commands.registerCommand('flt-edog.stop', stopDevMode),
        vscode.commands.registerCommand('flt-edog.revert', revertChanges),
        vscode.commands.registerCommand('flt-edog.refresh', refreshTokenNow),
        vscode.commands.registerCommand('flt-edog.copyToken', copyTokenToClipboard),
        vscode.commands.registerCommand('flt-edog.status', showStatus)
    );

    // Try to auto-detect config on activation
    tryAutoDetectConfig();
}

export function deactivate() {
    if (pythonProcess) {
        pythonProcess.kill();
    }
    if (checkInterval) {
        clearInterval(checkInterval);
    }
}

function updateStatusBar(text: string, tooltip: string) {
    statusBarItem.text = text;
    statusBarItem.tooltip = tooltip;
}

function getRepoRoot(): string | undefined {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
        return workspaceFolders[0].uri.fsPath;
    }
    return undefined;
}

function getPythonScriptPath(): string | undefined {
    const repoRoot = getRepoRoot();
    if (repoRoot) {
        const scriptPath = path.join(repoRoot, PYTHON_SCRIPT);
        if (fs.existsSync(scriptPath)) {
            return scriptPath;
        }
    }
    return undefined;
}

async function tryAutoDetectConfig() {
    const config = vscode.workspace.getConfiguration('flt-edog');
    if (!config.get('autoDetect')) {
        return;
    }

    const repoRoot = getRepoRoot();
    if (!repoRoot) {
        return;
    }

    // Try to find workload-dev-mode.json
    const devModeConfigPath = path.join(repoRoot, 'workload-dev-mode.json');
    if (fs.existsSync(devModeConfigPath)) {
        try {
            const content = fs.readFileSync(devModeConfigPath, 'utf-8');
            const devModeConfig = JSON.parse(content);
            
            // Extract IDs if present
            if (devModeConfig.workspaceId && !config.get('workspaceId')) {
                await config.update('workspaceId', devModeConfig.workspaceId, vscode.ConfigurationTarget.Workspace);
            }
            if (devModeConfig.capacityId && !config.get('capacityId')) {
                await config.update('capacityId', devModeConfig.capacityId, vscode.ConfigurationTarget.Workspace);
            }
            // Artifact ID might be in different locations
            const artifactId = devModeConfig.artifactId || devModeConfig.lakehouseId;
            if (artifactId && !config.get('artifactId')) {
                await config.update('artifactId', artifactId, vscode.ConfigurationTarget.Workspace);
            }
            
            console.log('Auto-detected config from workload-dev-mode.json');
        } catch (e) {
            console.log('Could not parse workload-dev-mode.json:', e);
        }
    }
}

async function getConfig(): Promise<{username: string, workspaceId: string, artifactId: string, capacityId: string} | null> {
    const config = vscode.workspace.getConfiguration('flt-edog');
    
    let workspaceId = config.get<string>('workspaceId') || '';
    let artifactId = config.get<string>('artifactId') || '';
    let capacityId = config.get<string>('capacityId') || '';
    let username = config.get<string>('username') || '';

    // If any required field is missing, prompt user
    if (!workspaceId || !artifactId || !capacityId) {
        const result = await vscode.window.showWarningMessage(
            'FLT EDOG: Missing configuration. Please configure workspace, artifact, and capacity IDs.',
            'Open Settings'
        );
        if (result === 'Open Settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'flt-edog');
        }
        return null;
    }

    return { username, workspaceId, artifactId, capacityId };
}

async function startDevMode() {
    if (isRunning) {
        vscode.window.showInformationMessage('FLT EDOG DevMode is already running');
        return;
    }

    const scriptPath = getPythonScriptPath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('Could not find get-edog-token.py in workspace root');
        return;
    }

    const config = await getConfig();
    if (!config) {
        return;
    }

    updateStatusBar('$(sync~spin) FLT EDOG: Starting...', 'Fetching token...');
    isRunning = true;

    // Build command args
    const args = [scriptPath];
    if (config.username) {
        args.push('-u', config.username);
    }
    args.push('-w', config.workspaceId);
    args.push('-a', config.artifactId);
    args.push('-c', config.capacityId);

    // Spawn Python process
    pythonProcess = spawn('python', args, {
        cwd: getRepoRoot()
    });

    let outputBuffer = '';

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        const text = data.toString();
        outputBuffer += text;
        console.log('[FLT EDOG]', text);

        // Parse token from output
        const tokenMatch = text.match(/Token acquired|Token refreshed/);
        if (tokenMatch) {
            // Extract expiry time
            const expiryMatch = text.match(/expires: (\d{2}:\d{2}:\d{2})/);
            if (expiryMatch) {
                const [hours, mins, secs] = expiryMatch[1].split(':').map(Number);
                const now = new Date();
                tokenExpiry = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, mins, secs);
                if (tokenExpiry < now) {
                    // Token expires tomorrow
                    tokenExpiry.setDate(tokenExpiry.getDate() + 1);
                }
            }
            updateStatusBarWithExpiry();
            vscode.window.showInformationMessage('FLT EDOG: Token acquired successfully!');
        }

        // Check for errors
        if (text.includes('❌ Failed')) {
            vscode.window.showErrorMessage('FLT EDOG: ' + text.split('❌')[1]?.split('\n')[0] || 'An error occurred');
        }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        console.error('[FLT EDOG Error]', data.toString());
    });

    pythonProcess.on('close', (code) => {
        console.log('[FLT EDOG] Process exited with code', code);
        isRunning = false;
        pythonProcess = null;
        updateStatusBar('$(shield) FLT EDOG: Stopped', 'Click to see status');
    });

    // Start periodic status bar updates
    checkInterval = setInterval(updateStatusBarWithExpiry, 60000); // Update every minute
}

function updateStatusBarWithExpiry() {
    if (!tokenExpiry) {
        updateStatusBar('$(shield) FLT EDOG: Active', 'Token active');
        return;
    }

    const now = new Date();
    const remaining = Math.floor((tokenExpiry.getTime() - now.getTime()) / 1000 / 60);
    
    if (remaining <= 0) {
        updateStatusBar('$(warning) FLT EDOG: Expired', 'Token has expired');
    } else if (remaining <= 10) {
        updateStatusBar(`$(warning) FLT EDOG: ${remaining}m`, `Token expires in ${remaining} minutes - refreshing soon`);
    } else {
        updateStatusBar(`$(shield) FLT EDOG: ${remaining}m`, `Token expires in ${remaining} minutes`);
    }
}

async function stopDevMode() {
    if (!isRunning || !pythonProcess) {
        vscode.window.showInformationMessage('FLT EDOG DevMode is not running');
        return;
    }

    pythonProcess.kill('SIGINT');
    isRunning = false;
    
    if (checkInterval) {
        clearInterval(checkInterval);
        checkInterval = null;
    }

    updateStatusBar('$(shield) FLT EDOG: Stopped', 'Click to see status');
    vscode.window.showInformationMessage('FLT EDOG DevMode stopped. Run "FLT EDOG: Revert" to undo changes.');
}

async function revertChanges() {
    const scriptPath = getPythonScriptPath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('Could not find get-edog-token.py in workspace root');
        return;
    }

    updateStatusBar('$(sync~spin) FLT EDOG: Reverting...', 'Reverting changes...');

    const revertProcess = spawn('python', [scriptPath, '--revert'], {
        cwd: getRepoRoot()
    });

    revertProcess.on('close', (code) => {
        if (code === 0) {
            vscode.window.showInformationMessage('FLT EDOG: All changes reverted successfully!');
            updateStatusBar('$(shield) FLT EDOG: Ready', 'Changes reverted');
        } else {
            vscode.window.showErrorMessage('FLT EDOG: Failed to revert some changes');
            updateStatusBar('$(warning) FLT EDOG: Revert failed', 'Some changes could not be reverted');
        }
    });
}

async function refreshTokenNow() {
    if (!isRunning) {
        vscode.window.showWarningMessage('FLT EDOG DevMode is not running. Start it first.');
        return;
    }

    // Send signal to refresh (or restart the process)
    vscode.window.showInformationMessage('FLT EDOG: Manual refresh requested. Restarting...');
    await stopDevMode();
    await startDevMode();
}

async function copyTokenToClipboard() {
    if (!currentToken) {
        vscode.window.showWarningMessage('No token available. Start FLT EDOG DevMode first.');
        return;
    }

    await vscode.env.clipboard.writeText(`MwcToken ${currentToken}`);
    vscode.window.showInformationMessage('FLT EDOG: Token copied to clipboard!');
}

async function showStatus() {
    const scriptPath = getPythonScriptPath();
    if (!scriptPath) {
        vscode.window.showErrorMessage('Could not find get-edog-token.py in workspace root');
        return;
    }

    // Run status check
    const statusProcess = spawn('python', [scriptPath, '--status'], {
        cwd: getRepoRoot()
    });

    let output = '';
    statusProcess.stdout?.on('data', (data: Buffer) => {
        output += data.toString();
    });

    statusProcess.on('close', () => {
        // Show in output channel
        const outputChannel = vscode.window.createOutputChannel('FLT EDOG DevMode');
        outputChannel.clear();
        outputChannel.appendLine('='.repeat(60));
        outputChannel.appendLine('FLT EDOG DevMode Status');
        outputChannel.appendLine('='.repeat(60));
        outputChannel.appendLine('');
        outputChannel.appendLine(`Running: ${isRunning ? 'Yes' : 'No'}`);
        if (tokenExpiry) {
            const remaining = Math.floor((tokenExpiry.getTime() - new Date().getTime()) / 1000 / 60);
            outputChannel.appendLine(`Token Expires: ${tokenExpiry.toLocaleTimeString()} (${remaining}m remaining)`);
        }
        outputChannel.appendLine('');
        outputChannel.appendLine('Code Changes:');
        outputChannel.appendLine(output);
        outputChannel.show();
    });
}

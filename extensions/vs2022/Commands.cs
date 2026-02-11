using Community.VisualStudio.Toolkit;
using Microsoft.VisualStudio.Shell;
using Task = System.Threading.Tasks.Task;

namespace FLTEdogDevMode
{
    [Command(PackageGuids.CommandSetGuidString, PackageIds.StartCommandId)]
    internal sealed class StartCommand : BaseCommand<StartCommand>
    {
        protected override async Task ExecuteAsync(OleMenuCmdEventArgs e)
        {
            await FLTEdogDevModePackage.Instance.StartDevModeAsync();
        }
    }

    [Command(PackageGuids.CommandSetGuidString, PackageIds.StopCommandId)]
    internal sealed class StopCommand : BaseCommand<StopCommand>
    {
        protected override async Task ExecuteAsync(OleMenuCmdEventArgs e)
        {
            await FLTEdogDevModePackage.Instance.StopDevModeAsync();
        }
    }

    [Command(PackageGuids.CommandSetGuidString, PackageIds.RevertCommandId)]
    internal sealed class RevertCommand : BaseCommand<RevertCommand>
    {
        protected override async Task ExecuteAsync(OleMenuCmdEventArgs e)
        {
            await FLTEdogDevModePackage.Instance.RevertChangesAsync();
        }
    }

    [Command(PackageGuids.CommandSetGuidString, PackageIds.RefreshCommandId)]
    internal sealed class RefreshCommand : BaseCommand<RefreshCommand>
    {
        protected override async Task ExecuteAsync(OleMenuCmdEventArgs e)
        {
            await FLTEdogDevModePackage.Instance.StopDevModeAsync();
            await FLTEdogDevModePackage.Instance.StartDevModeAsync();
        }
    }

    [Command(PackageGuids.CommandSetGuidString, PackageIds.StatusCommandId)]
    internal sealed class StatusCommand : BaseCommand<StatusCommand>
    {
        protected override async Task ExecuteAsync(OleMenuCmdEventArgs e)
        {
            await FLTEdogDevModePackage.Instance.ShowStatusAsync();
        }
    }
}

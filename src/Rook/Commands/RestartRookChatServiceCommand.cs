using Rhino;
using Rhino.Commands;
using Rook.UI.Chat;

namespace Rook.Commands
{
    /// <summary>
    /// Restart the Rhino-owned local chat service used by the Rook Chat panel.
    /// </summary>
    public class RestartRookChatServiceCommand : Command
    {
        public override string EnglishName => "RestartRookChatService";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            try
            {
                var health = ChatServiceManager.Instance.RestartAsync().GetAwaiter().GetResult();
                if (!health.ServiceAvailable)
                {
                    RhinoApp.WriteLine("Rook chat service restart failed: " + health.ServiceMessage);
                    return Result.Failure;
                }

                RhinoApp.WriteLine("Rook chat service restarted.");
                return Result.Success;
            }
            catch (System.Exception ex)
            {
                RhinoApp.WriteLine("Rook chat service restart failed: " + ex.Message);
                return Result.Failure;
            }
        }
    }
}

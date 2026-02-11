namespace FLTEdogDevMode
{
    public static class PackageGuids
    {
        public const string PackageGuidString = "5e8c8f4a-1234-4567-89ab-cdef01234567";
        public const string CommandSetGuidString = "5e8c8f4a-1234-4567-89ab-cdef01234568";
        
        public static readonly System.Guid PackageGuid = new System.Guid(PackageGuidString);
        public static readonly System.Guid CommandSetGuid = new System.Guid(CommandSetGuidString);
    }

    public static class PackageIds
    {
        public const int StartCommandId = 0x0100;
        public const int StopCommandId = 0x0101;
        public const int RevertCommandId = 0x0102;
        public const int RefreshCommandId = 0x0103;
        public const int StatusCommandId = 0x0104;
    }
}

namespace Rook.Bim
{
    internal static class BimCreationGuidProbeEvidenceClassifier
    {
        internal static BimCreationGuidProbeDocumentClass Classify(
            bool? isWorkshared,
            bool? isDetached,
            bool? isModelInCloud,
            bool? isFamilyDocument,
            bool? hasDocumentPath,
            bool? hasCentralModelPath,
            bool? serverPath,
            bool? cloudPath,
            bool? isCentral,
            bool? isLocal)
        {
            if (isDetached == true)
            {
                return BimCreationGuidProbeDocumentClass.Detached;
            }

            if (!isDetached.HasValue)
            {
                return BimCreationGuidProbeDocumentClass.Unknown;
            }

            if (!isWorkshared.HasValue)
            {
                return BimCreationGuidProbeDocumentClass.Unknown;
            }

            if (isWorkshared.Value)
            {
                if (isModelInCloud == true || cloudPath == true)
                {
                    return BimCreationGuidProbeDocumentClass.CloudWorkshared;
                }

                if (serverPath == true)
                {
                    return BimCreationGuidProbeDocumentClass.RevitServer;
                }

                if (ModelPathKind(hasCentralModelPath, serverPath, cloudPath) !=
                    BimCreationGuidProbeModelPathKind.File)
                {
                    return BimCreationGuidProbeDocumentClass.Unknown;
                }

                if (isCentral == true)
                {
                    return BimCreationGuidProbeDocumentClass.FileWorksharedCentral;
                }

                if (isLocal == true)
                {
                    return BimCreationGuidProbeDocumentClass.FileWorksharedLocal;
                }

                return BimCreationGuidProbeDocumentClass.FileWorksharedUnknownRole;
            }

            if (!isFamilyDocument.HasValue || !hasDocumentPath.HasValue)
            {
                return BimCreationGuidProbeDocumentClass.Unknown;
            }

            if (isFamilyDocument.Value)
            {
                return hasDocumentPath.Value
                    ? BimCreationGuidProbeDocumentClass.SavedFamily
                    : BimCreationGuidProbeDocumentClass.UnsavedFamily;
            }

            return hasDocumentPath.Value
                ? BimCreationGuidProbeDocumentClass.SavedNonWorksharedProject
                : BimCreationGuidProbeDocumentClass.UnsavedProject;
        }

        internal static BimCreationGuidProbeModelPathKind ModelPathKind(
            bool? hasCentralModelPath,
            bool? serverPath,
            bool? cloudPath)
        {
            if (cloudPath == true)
            {
                return BimCreationGuidProbeModelPathKind.Cloud;
            }

            if (serverPath == true)
            {
                return BimCreationGuidProbeModelPathKind.Server;
            }

            return hasCentralModelPath == true && serverPath == false && cloudPath == false
                ? BimCreationGuidProbeModelPathKind.File
                : BimCreationGuidProbeModelPathKind.Unknown;
        }
    }
}

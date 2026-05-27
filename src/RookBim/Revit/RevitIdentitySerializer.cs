using System;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    public static class RevitIdentitySerializer
    {
        private const int InvalidElementIdValue = -1;

        public static BimDocumentIdentity DocumentIdentity(Document document)
        {
            if (document == null)
            {
                throw new ArgumentNullException(nameof(document));
            }

            var centralGuid = GetWorksharingCentralGUID(document);
            return new BimDocumentIdentity
            {
                Guid = centralGuid.HasValue ? centralGuid.Value.ToString("D") : null,
                GuidSource = centralGuid.HasValue
                    ? BimDocumentGuidSource.RevitPersistentGuid
                    : BimDocumentGuidSource.Unavailable,
                Title = NullIfWhiteSpace(document.Title),
                Path = NullIfWhiteSpace(document.PathName),
                IsFamilyDocument = document.IsFamilyDocument,
                IsWorkshared = document.IsWorkshared
            };
        }

        public static BimViewIdentity ViewIdentity(View view)
        {
            if (view == null)
            {
                throw new ArgumentNullException(nameof(view));
            }

            return new BimViewIdentity
            {
                Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue,
                UniqueId = NullIfWhiteSpace(TryGetUniqueId(view)),
                Name = NullIfWhiteSpace(view.Name)
            };
        }

        public static BimElementIdentity ElementIdentity(Element element)
        {
            if (element == null)
            {
                throw new ArgumentNullException(nameof(element));
            }

            var document = element.Document;
            var documentIdentity = DocumentIdentity(document);
            var uniqueId = NullIfWhiteSpace(element.UniqueId);

            return new BimElementIdentity
            {
                Source = "revit",
                DocumentGuid = documentIdentity.Guid,
                DocumentGuidSource = documentIdentity.GuidSource,
                DocumentTitle = documentIdentity.Title,
                DocumentPath = documentIdentity.Path,
                ElementId = ToInt32OrNull(element.Id),
                UniqueId = uniqueId,
                FullUniqueId = uniqueId,
                Linked = false,
                Resolved = true,
                Confidence = BimIdentityConfidence.Exact
            };
        }

        private static Guid? GetWorksharingCentralGUID(Document document)
        {
            try
            {
                if (!document.IsWorkshared)
                {
                    return null;
                }

                var guid = document.WorksharingCentralGUID;
                return guid == Guid.Empty ? (Guid?)null : guid;
            }
            catch (Autodesk.Revit.Exceptions.InapplicableDataException)
            {
                return null;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static string? TryGetUniqueId(Element element)
        {
            try
            {
                return element.UniqueId;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }
    }
}

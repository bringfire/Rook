using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitSelectionService
    {
        public BimApiResponse Select(UIDocument uiDocument, BimSelectElementsRequest? request)
        {
            if (uiDocument == null)
            {
                throw new ArgumentNullException(nameof(uiDocument));
            }

            if (request == null || request.Identities == null || request.Identities.Count == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.InvalidScope,
                    "select-elements requires at least one element identity.",
                    400);
            }

            var ids = new List<ElementId>();
            var selectedIdentities = new List<BimElementIdentity>();
            var identities = request.Identities;

            foreach (var identity in identities)
            {
                var resolved = RevitIdentitySerializer.Resolve(uiDocument.Document, identity);
                if (!resolved.Success)
                {
                    return BimApiResponse.Fail(
                        resolved.ErrorCode,
                        resolved.Message ?? "One or more element identities did not resolve in the active Revit document.",
                        ResolveHttpStatus(resolved.ErrorCode));
                }

                ids.Add(resolved.Element!.Id);
                selectedIdentities.Add(RevitIdentitySerializer.ElementIdentity(resolved.Element!));
            }

            try
            {
                uiDocument.Selection.SetElementIds(ids);
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.SelectionFailed,
                    $"Revit UI selection failed: {ex.Message}",
                    409);
            }

            return BimApiResponse.Ok(new
            {
                selectedCount = ids.Count,
                identities = selectedIdentities,
                document = RevitIdentitySerializer.DocumentIdentity(uiDocument.Document)
            });
        }

        public BimApiResponse Clear(UIDocument uiDocument)
        {
            if (uiDocument == null)
            {
                throw new ArgumentNullException(nameof(uiDocument));
            }

            try
            {
                uiDocument.Selection.SetElementIds(new List<ElementId>());
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.SelectionFailed,
                    $"Revit UI selection clear failed: {ex.Message}",
                    409);
            }

            return BimApiResponse.Ok(new
            {
                selectedCount = 0,
                document = RevitIdentitySerializer.DocumentIdentity(uiDocument.Document)
            });
        }

        private static int ResolveHttpStatus(BimErrorCode code)
        {
            switch (code)
            {
                case BimErrorCode.DocumentMismatch:
                case BimErrorCode.LinkedElementUnsupported:
                    return 409;
                case BimErrorCode.ElementNotFound:
                    return 404;
                default:
                    return 400;
            }
        }
    }
}

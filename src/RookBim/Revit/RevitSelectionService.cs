using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitSelectionService
    {
        public BimApiResponse Select(
            UIDocument uiDocument,
            RevitDocumentIdentityEvidence evidence,
            BimSelectElementsRequest? request,
            BimDiagnosticContext diagnostics)
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

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(uiDocument.Document, evidence.Owner))
            {
                return BimApiResponse.Fail(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Selection document does not match the captured identity evidence.",
                    400);
            }

            var identities = request.Identities
                .Cast<BimElementIdentity?>()
                .ToList();
            var preflight = RevitDocumentIdentityResolver.PreflightBatch(
                evidence,
                identities,
                diagnostics);
            if (!preflight.Success)
            {
                return BimApiResponse.Fail(
                    preflight.ErrorCode,
                    preflight.Message ?? "One or more element identities failed preflight.",
                    RevitDocumentIdentityResolver.HttpStatusFor(preflight.ErrorCode));
            }

            var ids = new List<ElementId>();
            var selectedIdentities = new List<BimElementIdentity>();
            foreach (var identity in identities)
            {
                var resolved = RevitDocumentIdentityResolver.ResolveAfterPreflight(
                    evidence,
                    identity!);
                if (!resolved.Success)
                {
                    return BimApiResponse.Fail(
                        resolved.ErrorCode,
                        resolved.Message ?? "One or more element identities did not resolve in the active Revit document.",
                        RevitDocumentIdentityResolver.HttpStatusFor(resolved.ErrorCode));
                }

                ids.Add(resolved.Element!.Id);
                selectedIdentities.Add(
                    RevitDocumentIdentityResolver.ProjectElement(evidence, resolved.Element!));
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
                document = RevitDocumentIdentityResolver.ProjectDocument(evidence)
            });
        }

        public BimApiResponse Clear(
            UIDocument uiDocument,
            RevitDocumentIdentityEvidence evidence)
        {
            if (uiDocument == null)
            {
                throw new ArgumentNullException(nameof(uiDocument));
            }

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(uiDocument.Document, evidence.Owner))
            {
                return BimApiResponse.Fail(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Selection document does not match the captured identity evidence.",
                    400);
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
                document = RevitDocumentIdentityResolver.ProjectDocument(evidence)
            });
        }
    }
}

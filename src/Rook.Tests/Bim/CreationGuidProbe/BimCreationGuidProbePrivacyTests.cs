using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.CreationGuidProbe
{
    public sealed class BimCreationGuidProbePrivacyTests
    {
        [Fact]
        public void PublicReportSerialization_NeverEmitsRawProbeFixtures()
        {
            // Break caught: projecting a raw identity/path/title/message into the public report.
            const string rawTitle = "Top Secret Model";
            const string rawProjectPath = @"\\secret-server\secret-share\model.rvt";
            const string rawFamilyPath = @"\\secret-server\secret-share\family.rfa";
            const string rawGuid = "01234567-89ab-cdef-0123-456789abcdef";
            var rawException = new InvalidOperationException("line one\nsecret message");
            var session = new BimCreationGuidProbeSession(new BimCreationGuidProbeProvenance
            {
                ProcessId = 36032,
                RevitVersion = "2024.3",
                RhinoVersion = "8.0",
                RhinoInsideRevitVersion = "1.0",
                CoreVersion = "1.5.16",
                ModuleVersion = "1.5.16",
            });
            foreach (var caseId in Enum.GetValues(typeof(BimCreationGuidProbeCase))
                .Cast<BimCreationGuidProbeCase>())
            {
                var observation = new BimCreationGuidProbeObservation
                {
                    CaseId = caseId,
                    DocumentClass = BimCreationGuidProbeDocumentClass.SavedNonWorksharedProject,
                    CreationGuidFirstStatus = BimCreationGuidProbeReadStatus.Success,
                    CreationGuidSecondStatus = BimCreationGuidProbeReadStatus.Success,
                    CreationGuid = Guid.Parse(rawGuid),
                    CreationGuidNonEmpty = true,
                    CreationGuidStable = true,
                    DocumentPathStatus = BimCreationGuidProbeReadStatus.Success,
                    CanonicalDocumentPath = caseId == BimCreationGuidProbeCase.SavedFamily
                        ? rawFamilyPath
                        : caseId == BimCreationGuidProbeCase.UnsavedProject
                            ? rawTitle
                            : rawProjectPath,
                    FailureFacts = new[]
                    {
                        new BimCreationGuidProbeFailureFact(
                            BimCreationGuidProbeStage.DocumentPath,
                            rawException)
                    },
                };
                Assert.Equal(BimCreationGuidProbeSessionCode.Captured,
                    session.Capture(observation).Code);
            }

            var report = Assert.IsType<BimCreationGuidProbeReport>(session.Complete().Report);
            var options = new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            };
            options.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower));
            var json = JsonSerializer.Serialize(report, options);

            var unsavedProject = report.Captures.Single(capture =>
                capture.CaseId == BimCreationGuidProbeCase.UnsavedProject);
            var savedFamily = report.Captures.Single(capture =>
                capture.CaseId == BimCreationGuidProbeCase.SavedFamily);
            Assert.Null(unsavedProject.DocumentPathAlias);
            Assert.NotNull(savedFamily.DocumentPathAlias);
            Assert.All(report.Captures, capture => Assert.Equal(
                "System.InvalidOperationException",
                Assert.Single(capture.FailureFacts).ExceptionType));
            foreach (var rawValue in new[]
            {
                rawTitle, ".rvt", ".rfa", @"\\secret-server\secret-share",
                rawGuid, "line one", "secret message"
            })
            {
                Assert.DoesNotContain(rawValue, json, StringComparison.OrdinalIgnoreCase);
            }
            Assert.Contains("creation-001", json);
            Assert.Contains("path-001", json);
        }

        [Fact]
        public void FailureFact_NormalizesConstructedGenericTypeAndDropsBareMessage()
        {
            // Break caught: persisting a constructed generic name or raw exception message.
            var failure = new BimCreationGuidProbeFailureFact(
                BimCreationGuidProbeStage.CreationGuidFirst,
                new GenericProbeException<string>("SnowdonTowers"));

            Assert.Equal(
                "Rook.Tests.Bim.CreationGuidProbe.BimCreationGuidProbePrivacyTests+GenericProbeException`1",
                failure.ExceptionType);
            Assert.DoesNotContain("SnowdonTowers", failure.ExceptionType, StringComparison.Ordinal);
        }

        [Fact]
        public void FailureFact_CannotBeConstructedFromArbitraryStringEvidence()
        {
            // Break caught: reopening a string boundary that trusts a bare message as a type.
            Assert.Throws<MissingMethodException>(() => Activator.CreateInstance(
                typeof(BimCreationGuidProbeFailureFact),
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                binder: null,
                args: new object[]
                {
                    BimCreationGuidProbeStage.DocumentPath,
                    "Walls",
                    -2146233088,
                },
                culture: null));
        }

        [Fact]
        public void PublicDtos_ExposeNoRawOrMessageBearingMembers()
        {
            // Break caught: adding a public raw observation, exception, or title/path member.
            var publicDtos = new[]
            {
                typeof(BimCreationGuidProbeRequest),
                typeof(BimCreationGuidProbeCapture),
                typeof(BimCreationGuidProbeReport),
                typeof(BimCreationGuidProbeEqualityRelation),
                typeof(BimCreationGuidProbeFailureFact),
                typeof(BimCreationGuidProbeCompleteResult),
                typeof(BimCreationGuidProbeAbortResult),
                typeof(BimCreationGuidProbeProvenance),
                typeof(BimCreationGuidProbeCaptureResult),
            };
            foreach (var dto in publicDtos)
            {
                foreach (var member in dto.GetMembers(BindingFlags.Instance | BindingFlags.Public)
                    .Where(member => member.MemberType == MemberTypes.Field ||
                        member.MemberType == MemberTypes.Property))
                {
                    var memberType = member is PropertyInfo property
                        ? property.PropertyType : ((FieldInfo)member).FieldType;
                    Assert.NotEqual(typeof(Guid), Nullable.GetUnderlyingType(memberType) ?? memberType);
                    Assert.NotEqual(typeof(Exception), Nullable.GetUnderlyingType(memberType) ?? memberType);
                    Assert.NotEqual(typeof(object), Nullable.GetUnderlyingType(memberType) ?? memberType);
                    Assert.True(member.Name == "RawStateCleared" ||
                        !member.Name.StartsWith("Raw", StringComparison.Ordinal));
                    Assert.DoesNotContain("PathValue", member.Name, StringComparison.Ordinal);
                    Assert.DoesNotContain("Title", member.Name, StringComparison.Ordinal);
                    Assert.DoesNotContain("FileName", member.Name, StringComparison.Ordinal);
                    Assert.DoesNotContain("Message", member.Name, StringComparison.Ordinal);
                }
            }
        }

        [Theory]
        [MemberData(nameof(ActionCases))]
        public void ToWire_MapsEveryAction(BimCreationGuidProbeAction value, string wire) =>
            Assert.Equal(wire, BimCreationGuidProbeContracts.ToWire(value));

        [Theory]
        [MemberData(nameof(StatusCases))]
        public void ToWire_MapsEveryReadStatus(BimCreationGuidProbeReadStatus value, string wire) =>
            Assert.Equal(wire, BimCreationGuidProbeContracts.ToWire(value));

        [Theory]
        [MemberData(nameof(StageCases))]
        public void ToWire_MapsEveryStage(BimCreationGuidProbeStage value, string wire) =>
            Assert.Equal(wire, BimCreationGuidProbeContracts.ToWire(value));

        [Theory]
        [MemberData(nameof(CaseCases))]
        public void ToWire_MapsEveryCase(BimCreationGuidProbeCase value, string wire) =>
            Assert.Equal(wire, BimCreationGuidProbeContracts.ToWire(value));

        [Theory]
        [MemberData(nameof(ClassCases))]
        public void ToWire_MapsEveryDocumentClass(BimCreationGuidProbeDocumentClass value, string wire) =>
            Assert.Equal(wire, BimCreationGuidProbeContracts.ToWire(value));

        [Fact]
        public void ToWire_RejectsUndefinedClosedEnumValues()
        {
            // Break caught: an undefined input falling back to ToString and widening the protocol.
            Assert.Throws<ArgumentOutOfRangeException>(() => BimCreationGuidProbeContracts.ToWire((BimCreationGuidProbeAction)99));
            Assert.Throws<ArgumentOutOfRangeException>(() => BimCreationGuidProbeContracts.ToWire((BimCreationGuidProbeReadStatus)99));
            Assert.Throws<ArgumentOutOfRangeException>(() => BimCreationGuidProbeContracts.ToWire((BimCreationGuidProbeStage)99));
            Assert.Throws<ArgumentOutOfRangeException>(() => BimCreationGuidProbeContracts.ToWire((BimCreationGuidProbeCase)99));
            Assert.Throws<ArgumentOutOfRangeException>(() => BimCreationGuidProbeContracts.ToWire((BimCreationGuidProbeDocumentClass)99));
        }

        public static IEnumerable<object[]> ActionCases => Cases(
            (BimCreationGuidProbeAction.Begin, "begin"),
            (BimCreationGuidProbeAction.Capture, "capture"),
            (BimCreationGuidProbeAction.Complete, "complete"),
            (BimCreationGuidProbeAction.Abort, "abort"));

        public static IEnumerable<object[]> StatusCases => Cases(
            (BimCreationGuidProbeReadStatus.NotAttempted, "not_attempted"),
            (BimCreationGuidProbeReadStatus.Success, "success"),
            (BimCreationGuidProbeReadStatus.Failure, "failure"),
            (BimCreationGuidProbeReadStatus.NotApplicable, "not_applicable"));

        public static IEnumerable<object[]> StageCases => Cases(
            (BimCreationGuidProbeStage.IsWorkshared, "is_workshared"),
            (BimCreationGuidProbeStage.IsDetached, "is_detached"),
            (BimCreationGuidProbeStage.IsModelInCloud, "is_model_in_cloud"),
            (BimCreationGuidProbeStage.IsFamilyDocument, "is_family_document"),
            (BimCreationGuidProbeStage.CreationGuidFirst, "creation_guid_first"),
            (BimCreationGuidProbeStage.CreationGuidSecond, "creation_guid_second"),
            (BimCreationGuidProbeStage.DocumentPath, "document_path"),
            (BimCreationGuidProbeStage.CentralModelPath, "central_model_path"),
            (BimCreationGuidProbeStage.ModelPathServer, "model_path_server"),
            (BimCreationGuidProbeStage.ModelPathCloud, "model_path_cloud"),
            (BimCreationGuidProbeStage.ModelPathConvert, "model_path_convert"),
            (BimCreationGuidProbeStage.DocumentPathCanonicalize, "document_path_canonicalize"),
            (BimCreationGuidProbeStage.CentralPathCanonicalize, "central_path_canonicalize"),
            (BimCreationGuidProbeStage.BasicFileInfoExtract, "basic_file_info_extract"),
            (BimCreationGuidProbeStage.BasicFileInfoIsCentral, "basic_file_info_is_central"),
            (BimCreationGuidProbeStage.BasicFileInfoIsLocal, "basic_file_info_is_local"));

        public static IEnumerable<object[]> CaseCases => Cases(
            (BimCreationGuidProbeCase.SavedProjectInitial, "saved_project_initial"),
            (BimCreationGuidProbeCase.SavedProjectReopen, "saved_project_reopen"),
            (BimCreationGuidProbeCase.FileCentral, "file_central"),
            (BimCreationGuidProbeCase.FileLocal, "file_local"),
            (BimCreationGuidProbeCase.FileLocalReopen, "file_local_reopen"),
            (BimCreationGuidProbeCase.CopiedCentral, "copied_central"),
            (BimCreationGuidProbeCase.Detached, "detached"),
            (BimCreationGuidProbeCase.SavedFamily, "saved_family"),
            (BimCreationGuidProbeCase.UnsavedProject, "unsaved_project"),
            (BimCreationGuidProbeCase.UnsavedFamily, "unsaved_family"),
            (BimCreationGuidProbeCase.ReplacementSamePath, "replacement_same_path"));

        public static IEnumerable<object[]> ClassCases => Cases(
            (BimCreationGuidProbeDocumentClass.Unknown, "unknown"),
            (BimCreationGuidProbeDocumentClass.FileWorksharedCentral, "file_workshared_central"),
            (BimCreationGuidProbeDocumentClass.FileWorksharedLocal, "file_workshared_local"),
            (BimCreationGuidProbeDocumentClass.FileWorksharedUnknownRole, "file_workshared_unknown_role"),
            (BimCreationGuidProbeDocumentClass.RevitServer, "revit_server"),
            (BimCreationGuidProbeDocumentClass.CloudWorkshared, "cloud_workshared"),
            (BimCreationGuidProbeDocumentClass.SavedNonWorksharedProject, "saved_non_workshared_project"),
            (BimCreationGuidProbeDocumentClass.SavedFamily, "saved_family"),
            (BimCreationGuidProbeDocumentClass.Detached, "detached"),
            (BimCreationGuidProbeDocumentClass.UnsavedProject, "unsaved_project"),
            (BimCreationGuidProbeDocumentClass.UnsavedFamily, "unsaved_family"));

        private static IEnumerable<object[]> Cases<T>(params (T Value, string Wire)[] cases)
        {
            Assert.Equal(Enum.GetValues(typeof(T)).Cast<T>().OrderBy(value => value),
                cases.Select(item => item.Value).OrderBy(value => value));
            return cases.Select(item => new object[] { item.Value!, item.Wire });
        }

        private sealed class GenericProbeException<T> : Exception
        {
            internal GenericProbeException(string message)
                : base(message)
            {
            }
        }
    }
}

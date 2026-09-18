using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Rhino.Geometry;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(GrasshopperHandlerReadinessCollection.CollectionName)]
    public sealed class GrasshopperBehavioralSnapshotTests
    {
        private static readonly PropertyInfo ActiveCanvasProperty = CreateActiveCanvasProperty();

        [Fact]
        public void FencedSnapshot_ChecksFenceBeforeAnyReadInSameCallbackAndProjectsTypedPoints()
        {
            var events = new List<(string Name, int Thread)>();
            var output = new FakeOutput("P", new FakeVolatileData(
                2,
                new FakeGoo(new Point3d(0, 1, 2)),
                new FakeGoo(new Point3d(3, 4, 5)))
            {
                OnRead = () => events.Add(("volatile", Environment.CurrentManagedThreadId)),
            });
            var document = new FakeDocument(new FakePointComponent(output))
            {
                OnObjectsRead = () => events.Add(("objects", Environment.CurrentManagedThreadId)),
            };
            var registry = new GhSolveReceiptRegistry(
                fencedReadObserver: gate => events.Add(("fence", Environment.CurrentManagedThreadId)));
            var receipt = ReadyReceipt(registry, document);
            var handler = CreateHandler(document, registry);

            var response = handler.TakeSnapshot(FencedBody(receipt.ReceiptId, 3));

            Assert.True(response.Success);
            Assert.Equal(new[] { "fence", "objects", "volatile" }, events.Select(item => item.Name).Distinct());
            Assert.Single(events.Select(item => item.Thread).Distinct());
            var data = Element(response.Data);
            Assert.Equal(
                new[] { "behavioral_point_outputs", "components", "diagnostics", "document", "epoch", "flows", "readiness_fence", "version" },
                data.EnumerateObject().Select(item => item.Name).OrderBy(name => name));
            var fence = data.GetProperty("readiness_fence");
            Assert.Equal(
                new[] { "completed_solution_run_epoch", "document_session_id", "mutation_epoch", "readiness_receipt_id", "solution_run_epoch" },
                fence.EnumerateObject().Select(item => item.Name).OrderBy(name => name));
            Assert.Equal(receipt.ReceiptId, fence.GetProperty("readiness_receipt_id").GetString());
            Assert.Equal(receipt.DocumentSessionId, fence.GetProperty("document_session_id").GetString());
            Assert.Equal(receipt.MutationEpoch, fence.GetProperty("mutation_epoch").GetInt64());
            Assert.Equal(receipt.SolutionRunEpoch, fence.GetProperty("solution_run_epoch").GetInt64());
            Assert.Equal(receipt.CompletedSolutionRunEpoch, fence.GetProperty("completed_solution_run_epoch").GetInt64());
            var pointOutput = data.GetProperty("behavioral_point_outputs")[0];
            Assert.Equal(
                new[] { "complete", "component_id", "count", "error", "output_index", "output_name", "points" },
                pointOutput.EnumerateObject().Select(item => item.Name).OrderBy(name => name));
            Assert.Equal(2, pointOutput.GetProperty("count").GetInt32());
            Assert.True(pointOutput.GetProperty("complete").GetBoolean());
            Assert.Equal(JsonValueKind.Null, pointOutput.GetProperty("error").ValueKind);
            Assert.Equal("P", pointOutput.GetProperty("output_name").GetString());
            Assert.Equal(3d, pointOutput.GetProperty("points")[1][0].GetDouble());
        }

        [Fact]
        public void FencedSnapshot_ProjectsReceiptDocumentAndRejectsChangedCapturedDocumentBeforeRead()
        {
            var intended = new FakeDocument();
            var registry = new GhSolveReceiptRegistry();
            var receipt = ReadyReceipt(registry, intended, intended.DocumentID.ToString("D"));
            var intendedHandler = CreateHandler(intended, registry);

            var accepted = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(intended), intended),
                GhManagedDispatchScope.Observation,
                null,
                () => intendedHandler.TakeSnapshot(FencedBody(receipt.ReceiptId, 3)));

            Assert.True(accepted.Success);
            var acceptedData = Element(accepted.Data);
            Assert.Equal(
                intended.DocumentID.ToString("D"),
                acceptedData.GetProperty("ghDocumentId").GetString());
            Assert.Equal(
                intended.DocumentID.ToString("D"),
                acceptedData.GetProperty("readiness_fence").GetProperty("gh_document_id").GetString());

            var decoy = new FakeDocument();
            decoy.OnObjectsRead = () => throw new InvalidOperationException("snapshot data read");
            var decoyHandler = CreateHandler(decoy, registry);
            var refused = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(decoy), decoy),
                GhManagedDispatchScope.Observation,
                null,
                () => decoyHandler.TakeSnapshot(FencedBody(receipt.ReceiptId, 3)));

            Assert.False(refused.Success);
            Assert.Equal("gh_target_changed", Element(refused.Data).GetProperty("error").GetString());
            Assert.Equal(0, decoy.ObjectsReadCount);
        }

        [Fact]
        public void FencedSnapshot_RefusedReceiptsReadNoSnapshotData()
        {
            AssertRefused((registry, document) => "missing", "readiness_receipt_not_found_or_evicted_or_process_restarted");
            AssertRefused((registry, document) => registry.IssueMutation(document).Receipt!.ReceiptId, "readiness_receipt_not_ready");
            AssertRefused((registry, document) =>
            {
                var older = registry.IssueMutation(document).Receipt!;
                registry.IssueMutation(document);
                return older.ReceiptId;
            }, "readiness_receipt_superseded");
            AssertRefused((registry, document) =>
            {
                var receipt = registry.IssueMutation(document).Receipt!;
                registry.MarkSolverLocked(receipt.ReceiptId);
                return receipt.ReceiptId;
            }, "readiness_receipt_solver_locked");
            AssertRefused((registry, document) =>
            {
                var receipt = ReadyReceipt(registry, document);
                registry.OnSolutionStart(document);
                return receipt.ReceiptId;
            }, "readiness_receipt_stale_solution_run");
            AssertRefused((registry, document) =>
            {
                var receipt = ReadyReceipt(registry, document);
                registry.ReplaceDocument(new object());
                return receipt.ReceiptId;
            }, "readiness_receipt_document_replaced");
            AssertRefused((registry, document) =>
            {
                var receipt = registry.IssueMutation(document).Receipt!;
                registry.MarkMutationCommitUnknown(receipt.ReceiptId);
                return receipt.ReceiptId;
            }, "readiness_receipt_unknown");
        }

        [Fact]
        public void FencedSnapshot_WrongDocumentPendingExpiryAndTerminalEvictionReadNoSnapshotData()
        {
            var originalDocument = new FakeDocument();
            var wrongDocument = new FakeDocument { OnObjectsRead = () => throw new InvalidOperationException("data read") };
            var registry = new GhSolveReceiptRegistry();
            var receipt = ReadyReceipt(registry, originalDocument);
            var handler = CreateHandler(wrongDocument, registry);

            var wrongDocumentResponse = handler.TakeSnapshot(FencedBody(receipt.ReceiptId, 3));

            Assert.False(wrongDocumentResponse.Success);
            Assert.Equal(
                "readiness_receipt_document_replaced",
                Element(wrongDocumentResponse.Data).GetProperty("error").GetString());
            Assert.Equal(0, wrongDocument.ObjectsReadCount);

            var now = TimeSpan.Zero;
            var pendingRegistry = new GhSolveReceiptRegistry(monotonicNow: () => now);
            var pendingDocument = new FakeDocument { OnObjectsRead = () => throw new InvalidOperationException("data read") };
            var pendingReceipt = pendingRegistry.IssueMutation(pendingDocument).Receipt!;
            now = TimeSpan.FromMinutes(10);
            var pendingHandler = CreateHandler(pendingDocument, pendingRegistry);

            var pendingExpiredResponse = pendingHandler.TakeSnapshot(FencedBody(pendingReceipt.ReceiptId, 3));

            Assert.False(pendingExpiredResponse.Success);
            Assert.Equal(
                "readiness_receipt_expired",
                Element(pendingExpiredResponse.Data).GetProperty("error").GetString());
            Assert.Equal(0, pendingDocument.ObjectsReadCount);

            now = TimeSpan.Zero;
            var expiringRegistry = new GhSolveReceiptRegistry(monotonicNow: () => now);
            var expiringDocument = new FakeDocument { OnObjectsRead = () => throw new InvalidOperationException("data read") };
            var expiringReceipt = ReadyReceipt(expiringRegistry, expiringDocument);
            now = TimeSpan.FromMinutes(16);
            var expiringHandler = CreateHandler(expiringDocument, expiringRegistry);

            var expiredResponse = expiringHandler.TakeSnapshot(FencedBody(expiringReceipt.ReceiptId, 3));

            Assert.False(expiredResponse.Success);
            Assert.Equal(
                "readiness_receipt_not_found_or_evicted_or_process_restarted",
                Element(expiredResponse.Data).GetProperty("error").GetString());
            Assert.Equal(0, expiringDocument.ObjectsReadCount);
        }

        [Theory]
        [InlineData("not json")]
        [InlineData("[]")]
        [InlineData("{\"readiness_receipt_id\":\"id\"}")]
        [InlineData("{\"readiness_receipt_id\":\"id\",\"include_data\":false,\"max_preview_items\":3}")]
        [InlineData("{\"readiness_receipt_id\":\"id\",\"include_data\":true,\"max_preview_items\":0}")]
        [InlineData("{\"readiness_receipt_id\":\"id\",\"include_data\":true,\"max_preview_items\":1001}")]
        [InlineData("{\"readiness_receipt_id\":\"id\",\"include_data\":true,\"max_preview_items\":true}")]
        [InlineData("{\"readiness_receipt_id\":3,\"include_data\":true,\"max_preview_items\":3}")]
        [InlineData("{\"readiness_receipt_id\":\" \",\"include_data\":true,\"max_preview_items\":3}")]
        public void FencedSnapshot_InvalidRequestFailsBeforeFenceOrDataRead(string body)
        {
            var fenceChecks = 0;
            var registry = new GhSolveReceiptRegistry(fencedReadObserver: gate => fenceChecks++);
            var document = new FakeDocument { OnObjectsRead = () => throw new InvalidOperationException("data read") };
            var handler = CreateHandler(document, registry);

            var response = handler.TakeSnapshot(body);

            Assert.False(response.Success);
            Assert.Equal(0, fenceChecks);
            Assert.Equal(0, document.ObjectsReadCount);
        }

        [Fact]
        public void FencedSnapshot_TruncationMixedNonPointNonfiniteAndCountMismatchAreIncomplete()
        {
            AssertPointFailure(
                new FakeVolatileData(4,
                    new FakeGoo(new Point3d(0, 0, 0)),
                    new FakeGoo(new Point3d(1, 0, 0)),
                    new FakeGoo(new Point3d(2, 0, 0)),
                    new FakeGoo(new Point3d(3, 0, 0))),
                maxItems: 3,
                "truncated");
            AssertPointFailure(
                new FakeVolatileData(2, new FakeGoo(new Point3d(0, 0, 0)), new FakeGoo("not a point")),
                maxItems: 3,
                "non_point_item");
            AssertPointFailure(
                new FakeVolatileData(1, new FakeGoo(new Point3d(double.NaN, 0, 0))),
                maxItems: 3,
                "nonfinite_coordinate");
            AssertPointFailure(
                new FakeVolatileData(2, new FakeGoo(new Point3d(0, 0, 0))),
                maxItems: 3,
                "count_mismatch");
            AssertPointFailure(
                new FakeVolatileData(2,
                    new FakeGoo(new Point3d(0, 0, 0)),
                    new FakeGoo(new Point3d(1, 0, 0)))
                {
                    ThrowAfterFirst = true,
                },
                maxItems: 3,
                "data_unavailable");
        }

        [Fact]
        public void FencedSnapshot_AllNonpointOutputIsNotProjected()
        {
            var output = new FakeOutput("Text", new FakeVolatileData(1, new FakeGoo("not a point")));
            var document = new FakeDocument(new FakePointComponent(output));
            var registry = new GhSolveReceiptRegistry();
            var receipt = ReadyReceipt(registry, document);
            var handler = CreateHandler(document, registry);

            var response = handler.TakeSnapshot(FencedBody(receipt.ReceiptId, 3));

            Assert.True(response.Success);
            Assert.Empty(Element(response.Data).GetProperty("behavioral_point_outputs").EnumerateArray());
            Assert.Equal(1, output.VolatileDataReadCount);
        }

        [Fact]
        public void UnfencedSnapshotRetainsLegacyRootShapeAndNoBehavioralFields()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, new GhSolveReceiptRegistry());

            var response = handler.TakeSnapshot("{\"include_data\":true,\"max_preview_items\":3}");

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(
                new[] { "components", "diagnostics", "document", "epoch", "flows", "version" },
                data.EnumerateObject().Select(item => item.Name).OrderBy(name => name));
            Assert.False(data.TryGetProperty("readiness_fence", out _));
            Assert.False(data.TryGetProperty("behavioral_point_outputs", out _));
        }

        [Fact]
        public void ApplyEditEmbeddedStructuralSnapshotNeverContainsFencedEvidence()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, new GhSolveReceiptRegistry());

            var response = handler.ApplyEdit("{\"epoch\":0,\"groups\":[]}");

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.False(data.TryGetProperty("readiness_fence", out _));
            Assert.False(data.TryGetProperty("behavioral_point_outputs", out _));
        }

        private static void AssertRefused(
            Func<GhSolveReceiptRegistry, FakeDocument, string> receiptFactory,
            string expectedError)
        {
            var registry = new GhSolveReceiptRegistry();
            var document = new FakeDocument { OnObjectsRead = () => throw new InvalidOperationException("data read") };
            var receiptId = receiptFactory(registry, document);
            var handler = CreateHandler(document, registry);

            var response = handler.TakeSnapshot(FencedBody(receiptId, 3));

            Assert.False(response.Success);
            Assert.Equal(expectedError, Element(response.Data).GetProperty("error").GetString());
            Assert.Equal(0, document.ObjectsReadCount);
        }

        private static void AssertPointFailure(FakeVolatileData volatileData, int maxItems, string expectedError)
        {
            var outputParam = new FakeOutput("P", volatileData);
            var document = new FakeDocument(new FakePointComponent(outputParam));
            var registry = new GhSolveReceiptRegistry();
            var receipt = ReadyReceipt(registry, document);
            var handler = CreateHandler(document, registry);

            var response = handler.TakeSnapshot(FencedBody(receipt.ReceiptId, maxItems));

            Assert.True(response.Success);
            var output = Element(response.Data).GetProperty("behavioral_point_outputs")[0];
            Assert.False(output.GetProperty("complete").GetBoolean());
            Assert.Equal(expectedError, output.GetProperty("error").GetString());
            Assert.Equal(1, outputParam.VolatileDataReadCount);
        }

        private static GhSolveReadinessReceipt ReadyReceipt(
            GhSolveReceiptRegistry registry,
            object document,
            string? ghDocumentId = null)
        {
            var receipt = registry.IssueMutation(document, ghDocumentId).Receipt!;
            registry.MarkScheduleAccepted(receipt.ReceiptId);
            registry.OnSolutionStart(document);
            registry.OnSolutionEnd(document);
            return registry.Get(receipt.ReceiptId).Receipt!;
        }

        private static GrasshopperHandler CreateHandler(object document, GhSolveReceiptRegistry registry)
        {
            ActiveCanvasProperty.SetValue(null, new FakeCanvas(document));
            return new GrasshopperHandler(
                bridgeCore: new ReadyCore((FakeDocument)document),
                runningAsRhinoInside: () => false,
                solveReceiptRegistry: registry,
                solutionLifecycleAdapter: new GhSolutionLifecycleAdapter(),
                canvasDocumentLifecycleAdapter: new GhCanvasDocumentLifecycleAdapter());
        }

        private static string FencedBody(string receiptId, int maxItems) => JsonSerializer.Serialize(new
        {
            readiness_receipt_id = receiptId,
            include_data = true,
            max_preview_items = maxItems,
        });

        private static JsonElement Element(object? value) => JsonSerializer.SerializeToElement(value);

        private static PropertyInfo CreateActiveCanvasProperty()
        {
            RuntimeHelpers.RunClassConstructor(typeof(GrasshopperTerminalMutationReceiptTests).TypeHandle);
            return AppDomain.CurrentDomain.GetAssemblies()
                .Single(assembly => assembly.GetName().Name == "Grasshopper")
                .GetType("Grasshopper.Instances")!
                .GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static)!;
        }

        private sealed class ReadyCore : IGrasshopperCore
        {
            private readonly FakeDocument _document;

            public ReadyCore(FakeDocument document) => _document = document;

            public BridgeResult<GrasshopperStatusDto> GetStatus()
            {
                _ = _document.Objects.Count;
                return BridgeResult<GrasshopperStatusDto>.Ok(new GrasshopperStatusDto
                {
                    Available = true,
                    HasActiveCanvas = true,
                    HasActiveDocument = true,
                    CanvasVisible = true,
                    ReadyForEdit = true,
                });
            }

            public BridgeResult<GrasshopperDocumentInfoDto> GetDocumentInfo() =>
                BridgeResult<GrasshopperDocumentInfoDto>.Ok(new GrasshopperDocumentInfoDto());
            public BridgeResult<GrasshopperQueryDto> QueryDocument() =>
                BridgeResult<GrasshopperQueryDto>.Ok(new GrasshopperQueryDto());
            public BridgeResult<GrasshopperSelectionDto> GetSelection() =>
                BridgeResult<GrasshopperSelectionDto>.Ok(new GrasshopperSelectionDto());
        }

        public sealed class FakeCanvas
        {
            public FakeCanvas(object document) => Document = document;
            public object Document { get; }
            public void Refresh() { }
        }

        public sealed class FakeDocument
        {
            private readonly List<object> _objects;
            public FakeDocument(params object[] objects) => _objects = objects.ToList();
            public Guid DocumentID { get; } = Guid.NewGuid();
            public Action? OnObjectsRead { get; set; }
            public int ObjectsReadCount { get; private set; }
            public bool Enabled { get; set; } = true;
            public IReadOnlyList<object> Objects
            {
                get
                {
                    ObjectsReadCount++;
                    OnObjectsRead?.Invoke();
                    return _objects;
                }
            }
        }

        private sealed class FixedDispatchSource : IGrasshopperDispatchSource
        {
            private readonly object _canvas;
            private readonly object _document;

            internal FixedDispatchSource(object canvas, object document)
            {
                _canvas = canvas;
                _document = document;
            }

            public GrasshopperDispatchCapture Capture() =>
                GrasshopperDispatchCapture.Available(
                    typeof(FixedDispatchSource).Assembly,
                    _canvas,
                    _document);
        }

        public sealed class FakePointComponent
        {
            public FakePointComponent(params FakeOutput[] outputs)
            {
                InstanceGuid = Guid.NewGuid();
                Params = new FakeParams(outputs);
            }
            public Guid InstanceGuid { get; }
            public string Name => "Point Output";
            public string NickName => "Point Output";
            public FakeParams Params { get; }
        }

        public sealed class FakeParams
        {
            public FakeParams(IEnumerable<FakeOutput> outputs) => Output = outputs.ToList();
            public IReadOnlyList<object> Input { get; } = Array.Empty<object>();
            public IReadOnlyList<FakeOutput> Output { get; }
        }

        public sealed class FakeOutput
        {
            private readonly FakeVolatileData _volatileData;
            public FakeOutput(string name, FakeVolatileData volatileData)
            {
                Name = name;
                NickName = name;
                _volatileData = volatileData;
            }
            public string Name { get; }
            public string NickName { get; }
            public string TypeName => "Point";
            public IReadOnlyList<object> Recipients { get; } = Array.Empty<object>();
            public int VolatileDataReadCount { get; private set; }
            public FakeVolatileData VolatileData
            {
                get
                {
                    VolatileDataReadCount++;
                    _volatileData.OnRead?.Invoke();
                    return _volatileData;
                }
            }
        }

        public sealed class FakeVolatileData
        {
            private readonly IReadOnlyList<FakeGoo> _items;
            public FakeVolatileData(int dataCount, params FakeGoo[] items)
            {
                DataCount = dataCount;
                _items = items;
            }
            public Action? OnRead { get; set; }
            public bool ThrowAfterFirst { get; set; }
            public bool IsEmpty => DataCount == 0;
            public int PathCount => DataCount == 0 ? 0 : 1;
            public int DataCount { get; }
            public IEnumerable<FakeGoo> AllData(bool includeNulls)
            {
                for (var index = 0; index < _items.Count; index++)
                {
                    if (ThrowAfterFirst && index > 0)
                        throw new InvalidOperationException("volatile enumeration failed");
                    yield return _items[index];
                }
            }
        }

        public sealed class FakeGoo
        {
            public FakeGoo(object value) => Value = value;
            public object Value { get; }
            public override string ToString() => "STRING_PREVIEW_MUST_NOT_BE_ACCEPTANCE";
        }
    }
}

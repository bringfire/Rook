using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(GrasshopperHandlerReadinessCollection.CollectionName)]
    public sealed class GrasshopperTerminalMutationReceiptTests
    {
        private static readonly PropertyInfo ActiveCanvasProperty = CreateActiveCanvasProperty();

        [Fact]
        public void SetValue_FailureBeforeCommitRetainsClosedFailureAndTerminalReceipt()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid(), new MissingValueSlider());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);

            var response = handler.SetValue(JsonSerializer.Serialize(new
            {
                guid = slider.InstanceGuid,
                value = 5m,
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal(
                new[] { "error", "message", "solve_relevant_mutation_committed", "solve_readiness_receipt" },
                data.EnumerateObject().Select(item => item.Name).ToArray());
            Assert.Equal("set_value_failed", data.GetProperty("error").GetString());
            Assert.False(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetValue_PreReservationExceptionKeepsLegacyFailureString()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider) { ThrowOnObjectsRead = true };
            var handler = CreateHandler(document);

            var response = handler.SetValue(JsonSerializer.Serialize(new
            {
                guid = slider.InstanceGuid,
                value = 5m,
            }));

            Assert.False(response.Success);
            Assert.IsType<string>(response.Data);
            Assert.StartsWith("SetValue failed: ", (string)response.Data!);
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetValue_ThrowingFirstMutatorMarksCommitUnknown()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.TypedSlider!.ThrowOnValueSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);

            var response = handler.SetValue(JsonSerializer.Serialize(new
            {
                guid = slider.InstanceGuid,
                value = 5m,
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal(JsonValueKind.Null, data.GetProperty("solve_relevant_mutation_committed").ValueKind);
            Assert.Equal(
                "mutation_commit_unknown",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetValue_ThrowingFirstRangeMutatorMarksCommitUnknown()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.TypedSlider!.ThrowOnMinimumSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);

            var response = handler.SetValue(JsonSerializer.Serialize(new
            {
                guid = slider.InstanceGuid,
                min = -10m,
                value = 5m,
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal(JsonValueKind.Null, data.GetProperty("solve_relevant_mutation_committed").ValueKind);
            Assert.Equal(
                "mutation_commit_unknown",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetValue_FailureAfterKnownCommitSchedulesOnceAndRetainsPendingReceipt()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.TypedSlider!.ThrowOnValueSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);

            var response = handler.SetValue(JsonSerializer.Serialize(new
            {
                guid = slider.InstanceGuid,
                min = -10m,
                value = 5m,
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.True(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(-10m, slider.TypedSlider.Minimum);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_SourceWriteReturnsManagedReceiptAlongsideCommitEvidence()
        {
            var component = new FakeScriptComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new
            {
                guid = component.InstanceGuid,
                script = "print('ready')",
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.True(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal("print('ready')", component.Source);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_PreReservationExceptionKeepsLegacyFailureString()
        {
            var component = new FakeScriptComponent(Guid.NewGuid());
            var document = new FakeDocument(component) { ThrowOnObjectsRead = true };
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new
            {
                guid = component.InstanceGuid,
                script = "print('not reached')",
            }));

            Assert.False(response.Success);
            Assert.IsType<string>(response.Data);
            Assert.StartsWith("SetScript failed: ", (string)response.Data!);
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_LaterFailurePreservesKnownCommitAndSchedulesOnce()
        {
            var component = new FakeScriptComponent(Guid.NewGuid()) { ThrowOnExpire = true };
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new
            {
                guid = component.InstanceGuid,
                script = "print('committed')",
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal(
                new[] { "error", "message", "solve_relevant_mutation_committed", "solve_readiness_receipt" },
                data.EnumerateObject().Select(item => item.Name).ToArray());
            Assert.Equal("set_script_failed", data.GetProperty("error").GetString());
            Assert.True(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal("print('committed')", component.Source);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_ReadRemainsObservationalAndReceiptFree()
        {
            var component = new FakeScriptComponent(Guid.NewGuid());
            component.SetSource("print('existing')");
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new { guid = component.InstanceGuid }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal("get", data.GetProperty("Action").GetString());
            Assert.False(data.TryGetProperty("solve_readiness_receipt", out _));
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_GroupOnlyRequestDoesNotIssueReadyReceiptOrSchedule()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit("{\"epoch\":0,\"groups\":[{}]}");

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.False(data.TryGetProperty("solve_readiness_receipt", out _));
            Assert.Equal(0, document.ScheduleCount);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("created").GetInt32());
        }

        [Fact]
        public void ApplyEdit_RequestedButZeroCommitReturnsTerminalNonreadyReceipt()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit("{\"epoch\":0,\"set_values\":[{\"id\":\"missing\",\"value\":1}]}");

            Assert.True(response.Success);
            var receipt = Element(response.Data).GetProperty("solve_readiness_receipt");
            Assert.Equal("unknown", receipt.GetProperty("status").GetString());
            Assert.Equal("no_solve_relevant_mutation_committed", receipt.GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_PartialCommittedBatchRetainsReceiptAndSchedulesOnce()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new object[]
                {
                    new { id = "C1", value = 7m },
                    new { id = "missing", value = 9m },
                },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(7m, slider.TypedSlider!.Value);
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("values_set").GetInt32());
            Assert.NotEqual(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_CommittedBatchReturnsPendingReceiptAndSchedulesOnce()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 3m } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(3m, slider.TypedSlider!.Value);
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("values_set").GetInt32());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_CommittedBatchWithLockedSolverReturnsNonreadyReceiptWithoutScheduling()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document, globalSolutionsEnabled: false);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 4m } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            var receipt = data.GetProperty("solve_readiness_receipt");
            Assert.Equal("solver_locked", receipt.GetProperty("status").GetString());
            Assert.Equal("solver_locked", receipt.GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_CommittedBatchWithUnknownScheduleReturnsUnknownReceiptWithoutRetry()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider) { ThrowOnSchedule = true };
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 6m } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            var receipt = data.GetProperty("solve_readiness_receipt");
            Assert.Equal("unknown", receipt.GetProperty("status").GetString());
            Assert.Equal("schedule_acceptance_unknown", receipt.GetProperty("reason").GetString());
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_ExceptionAfterCommitRetainsCountsAndReceipt()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid()) { ThrowOnExpire = true };
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 11m } },
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal("apply_edit_failed", data.GetProperty("error").GetString());
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("values_set").GetInt32());
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(11m, slider.TypedSlider!.Value);
            Assert.Equal(1, document.ScheduleCount);
        }

        private static GrasshopperHandler CreateHandler(
            FakeDocument document,
            bool globalSolutionsEnabled = true)
        {
            FakeDocument.EnableSolutions = globalSolutionsEnabled;
            ActiveCanvasProperty.SetValue(null, new FakeCanvas(document));
            return new GrasshopperHandler(
                bridgeCore: new ReadyCore(),
                runningAsRhinoInside: () => false,
                solveReceiptRegistry: new GhSolveReceiptRegistry(),
                solutionLifecycleAdapter: new GhSolutionLifecycleAdapter(),
                canvasDocumentLifecycleAdapter: new GhCanvasDocumentLifecycleAdapter());
        }

        private static JsonElement Element(object? value) => JsonSerializer.SerializeToElement(value);

        private static PropertyInfo CreateActiveCanvasProperty()
        {
            var existing = AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(assembly => assembly.GetName().Name == "Grasshopper")
                ?.GetType("Grasshopper.Instances")
                ?.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static);
            if (existing != null)
            {
                return existing;
            }

            var assembly = AppDomain.CurrentDomain.DefineDynamicAssembly(
                new AssemblyName("Grasshopper"),
                AssemblyBuilderAccess.Run);
            var module = assembly.DefineDynamicModule("Grasshopper");
            var type = module.DefineType(
                "Grasshopper.Instances",
                TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
            var field = type.DefineField("_activeCanvas", typeof(object), FieldAttributes.Private | FieldAttributes.Static);
            var property = type.DefineProperty("ActiveCanvas", PropertyAttributes.None, typeof(object), Type.EmptyTypes);
            var getter = type.DefineMethod(
                "get_ActiveCanvas",
                MethodAttributes.Public | MethodAttributes.Static | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(object),
                Type.EmptyTypes);
            var getterIl = getter.GetILGenerator();
            getterIl.Emit(OpCodes.Ldsfld, field);
            getterIl.Emit(OpCodes.Ret);
            var setter = type.DefineMethod(
                "set_ActiveCanvas",
                MethodAttributes.Public | MethodAttributes.Static | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                null,
                new[] { typeof(object) });
            var setterIl = setter.GetILGenerator();
            setterIl.Emit(OpCodes.Ldarg_0);
            setterIl.Emit(OpCodes.Stsfld, field);
            setterIl.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
            property.SetSetMethod(setter);
            return type.CreateType()!.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static)!;
        }

        private sealed class ReadyCore : IGrasshopperCore
        {
            public BridgeResult<GrasshopperStatusDto> GetStatus() =>
                BridgeResult<GrasshopperStatusDto>.Ok(new GrasshopperStatusDto
                {
                    Available = true,
                    HasActiveCanvas = true,
                    HasActiveDocument = true,
                    CanvasVisible = true,
                    ReadyForEdit = true,
                });

            public BridgeResult<GrasshopperDocumentInfoDto> GetDocumentInfo() =>
                BridgeResult<GrasshopperDocumentInfoDto>.Ok(new GrasshopperDocumentInfoDto());

            public BridgeResult<GrasshopperQueryDto> QueryDocument() =>
                BridgeResult<GrasshopperQueryDto>.Ok(new GrasshopperQueryDto());

            public BridgeResult<GrasshopperSelectionDto> GetSelection() =>
                BridgeResult<GrasshopperSelectionDto>.Ok(new GrasshopperSelectionDto());
        }

        public sealed class FakeCanvasDocumentChangedEventArgs : EventArgs
        {
            public FakeCanvasDocumentChangedEventArgs(object? oldDocument, object? newDocument)
            {
                OldDocument = oldDocument;
                NewDocument = newDocument;
            }

            public object? OldDocument { get; }
            public object? NewDocument { get; }
        }

        public sealed class FakeCanvas
        {
            public FakeCanvas(object document) => Document = document;

            public object? Document { get; private set; }
            public event EventHandler<FakeCanvasDocumentChangedEventArgs>? DocumentChanged;

            public void Refresh() { }
        }

        public sealed class FakeSolutionEventArgs : EventArgs
        {
            public FakeSolutionEventArgs(object document) => Document = document;
            public object Document { get; }
        }

        public sealed class FakeDocument
        {
            private readonly IReadOnlyList<object> _objects;

            public FakeDocument(params object[] objects) => _objects = objects;

            public static bool EnableSolutions { get; set; } = true;
            public bool Enabled { get; set; } = true;
            public bool ThrowOnObjectsRead { get; set; }
            public IReadOnlyList<object> Objects
            {
                get
                {
                    if (ThrowOnObjectsRead)
                    {
                        throw new InvalidOperationException("objects unavailable before reservation");
                    }

                    return _objects;
                }
            }
            public int ScheduleCount { get; private set; }
            public bool ThrowOnSchedule { get; set; }
            public FakeUndoUtil UndoUtil { get; } = new();
            public event EventHandler<FakeSolutionEventArgs>? SolutionStart;
            public event EventHandler<FakeSolutionEventArgs>? SolutionEnd;

            public void ScheduleSolution(int delayMs)
            {
                ScheduleCount++;
                if (ThrowOnSchedule)
                {
                    throw new InvalidOperationException("schedule acceptance unknown");
                }
            }
        }

        public sealed class FakeUndoUtil
        {
            public void RecordGenericObjectEvent(string name, object documentObject) { }
        }

        public sealed class GH_NumberSlider
        {
            public GH_NumberSlider(Guid instanceGuid, object? slider = null)
            {
                InstanceGuid = instanceGuid;
                Slider = slider ?? new FakeSlider();
                TypedSlider = Slider as FakeSlider;
            }

            public Guid InstanceGuid { get; }
            public object Slider { get; }
            public FakeSlider? TypedSlider { get; }
            public bool ThrowOnExpire { get; set; }

            public void ExpireSolution(bool recompute)
            {
                if (ThrowOnExpire)
                {
                    throw new InvalidOperationException("expire failed after commit");
                }
            }
        }

        public sealed class MissingValueSlider
        {
            public decimal Minimum { get; set; }
            public decimal Maximum { get; set; } = 100m;
        }

        public sealed class FakeSlider
        {
            private decimal _value;
            private decimal _minimum;

            public bool ThrowOnMinimumSet { get; set; }
            public decimal Minimum
            {
                get => _minimum;
                set
                {
                    if (ThrowOnMinimumSet)
                    {
                        throw new InvalidOperationException("minimum mutation failed");
                    }

                    _minimum = value;
                }
            }
            public decimal Maximum { get; set; } = 100m;
            public bool ThrowOnValueSet { get; set; }
            public decimal Value
            {
                get => _value;
                set
                {
                    if (ThrowOnValueSet)
                    {
                        throw new InvalidOperationException("value mutation failed");
                    }

                    _value = value;
                }
            }
        }

        public sealed class FakeScriptComponent
        {
            public FakeScriptComponent(Guid instanceGuid) => InstanceGuid = instanceGuid;

            public Guid InstanceGuid { get; }
            public string Source { get; private set; } = string.Empty;
            public bool ThrowOnExpire { get; set; }

            public void SetSource(string source) => Source = source;

            public bool TryGetSource(out string source)
            {
                source = Source;
                return true;
            }

            public void ExpireSolution(bool recompute)
            {
                if (ThrowOnExpire)
                {
                    throw new InvalidOperationException("expire failed after script commit");
                }
            }
        }
    }
}

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
            Assert.False(data.GetProperty("solve_readiness_receipt").TryGetProperty("gh_document_id", out _));
            Assert.False(data.TryGetProperty("ghDocumentId", out _));
            Assert.Equal("print('ready')", component.Source);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_PanelDispatchProjectsCapturedDocumentIdentity()
        {
            var component = new FakeScriptComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(document), document),
                GhManagedDispatchScope.Mutation,
                document.DocumentID.ToString("D"),
                () => handler.SetScript(JsonSerializer.Serialize(new
                {
                    guid = component.InstanceGuid,
                    script = "print('ready')",
                })));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(
                document.DocumentID.ToString("D"),
                data.GetProperty("solve_readiness_receipt").GetProperty("gh_document_id").GetString());
            Assert.Equal(document.DocumentID.ToString("D"), data.GetProperty("ghDocumentId").GetString());
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
        public void SetScript_NullLegacySourceAfterReservationIsKnownZeroCommit()
        {
            var component = new FakeLegacyScriptComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new
            {
                guid = component.InstanceGuid,
                script = "print('not written')",
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.False(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void SetScript_ThrowingSourceMutatorAfterReservationIsUnknownCommit()
        {
            var component = new FakeScriptComponent(Guid.NewGuid()) { ThrowOnSetSource = true };
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);

            var response = handler.SetScript(JsonSerializer.Serialize(new
            {
                guid = component.InstanceGuid,
                script = "print('unknown')",
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

            var response = handler.ApplyEdit("{\"epoch\":0,\"set_values\":[{\"id\":\"C999\",\"value\":1}]}");

            Assert.True(response.Success);
            var receipt = Element(response.Data).GetProperty("solve_readiness_receipt");
            Assert.Equal("unknown", receipt.GetProperty("status").GetString());
            Assert.Equal("no_solve_relevant_mutation_committed", receipt.GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_ValidatedSliderItemWithoutMutationFieldsIsZeroCommit()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1" } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("values_set").GetInt32());
            Assert.Contains(
                "no mutable fields",
                data.GetProperty("edit_summary").GetProperty("errors")[0].GetString());
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_RangeCommitBeforeThrowingValueRetainsCommitAndSchedulesOnce()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.TypedSlider!.ThrowOnValueSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", max = 20m, value = 7m } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(20m, slider.TypedSlider.Maximum);
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("values_set").GetInt32());
            Assert.NotEqual(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_FirstThrowingValueMutatorProducesUnknownCommitWithoutSchedule()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.TypedSlider!.ThrowOnValueSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 7m } },
            }));

            Assert.True(response.Success);
            var receipt = Element(response.Data).GetProperty("solve_readiness_receipt");
            Assert.Equal("unknown", receipt.GetProperty("status").GetString());
            Assert.Equal("mutation_commit_unknown", receipt.GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_ReservationCapacityRefusalMutatesNothing()
        {
            var registry = new GhSolveReceiptRegistry();
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document, registry: registry);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();
            registry.ReplaceDocument(document);
            var capacityDocuments = new List<object>();
            for (var i = 0; i < 64; i++)
            {
                var capacityDocument = new object();
                capacityDocuments.Add(capacityDocument);
                Assert.True(registry.IssueMutation(capacityDocument).Issued);
            }

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                set_values = new[] { new { id = "C1", value = 9m } },
            }));

            Assert.False(response.Success);
            Assert.Equal(0m, slider.TypedSlider!.Value);
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_DeleteCommitsOnceAndReturnsReceipt()
        {
            var component = new FakeDeletableComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document);
            var snapshot = Element(handler.TakeSnapshot(null).Data);
            var epoch = snapshot.GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                delete = new[] { "C1" },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("deleted").GetInt32());
            Assert.Empty(document.Objects);
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_DeleteFalseReturnDoesNotManufactureCommit()
        {
            var component = new FakeDeletableComponent(Guid.NewGuid());
            var document = new FakeDocument(component) { RemoveResult = false };
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                delete = new[] { "C1" },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("deleted").GetInt32());
            Assert.Contains("returned false", data.GetProperty("edit_summary").GetProperty("errors")[0].GetString());
            Assert.Single(document.Objects);
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_ConnectAndDisconnectEachCountOnlyConfirmedMutatorReturn()
        {
            var source = CreateDynamicParam(Guid.NewGuid());
            var target = CreateDynamicParam(Guid.NewGuid());
            var document = new FakeDocument(source, target);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var connectedResponse = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                connect = new[] { "C1.O0>C2.I0" },
            }));

            Assert.True(connectedResponse.Success);
            var connectedData = Element(connectedResponse.Data);
            Assert.Equal(1, connectedData.GetProperty("edit_summary").GetProperty("connected").GetInt32());
            Assert.Equal(1, GetDynamicParamCount(target, "AddCalls"));
            Assert.Equal("pending", connectedData.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());

            epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();
            var disconnectedResponse = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                disconnect = new[] { "C1.O0>C2.I0" },
            }));

            Assert.True(disconnectedResponse.Success);
            var disconnectedData = Element(disconnectedResponse.Data);
            Assert.Equal(1, disconnectedData.GetProperty("edit_summary").GetProperty("disconnected").GetInt32());
            Assert.Equal(1, GetDynamicParamCount(target, "RemoveCalls"));
            Assert.Equal("pending", disconnectedData.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Equal(2, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_MissingConnectMutatorIsZeroCommitInsteadOfPhantomCommit()
        {
            var source = new FakeSimpleParam(Guid.NewGuid());
            var target = new FakeSimpleParam(Guid.NewGuid());
            var document = new FakeDocument(source, target);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                connect = new[] { "C1.O0>C2.I0" },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("connected").GetInt32());
            Assert.Contains("AddSource mutator unavailable", data.GetProperty("edit_summary").GetProperty("errors")[0].GetString());
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_MissingDisconnectMutatorIsZeroCommitInsteadOfPhantomCommit()
        {
            var source = new FakeSimpleParam(Guid.NewGuid());
            var target = new FakeSimpleParam(Guid.NewGuid());
            var document = new FakeDocument(source, target);
            var handler = CreateHandler(document);
            var epoch = Element(handler.TakeSnapshot(null).Data).GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                disconnect = new[] { "C1.O0>C2.I0" },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("disconnected").GetInt32());
            Assert.Contains("RemoveSource mutator unavailable", data.GetProperty("edit_summary").GetProperty("errors")[0].GetString());
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_MissingDeleteMutatorIsZeroCommitInsteadOfPhantomCommit()
        {
            var component = new FakeDeletableComponent(Guid.NewGuid());
            var document = new FakeDocumentWithoutRemove(component);
            var handler = CreateHandler(document);
            var snapshot = Element(handler.TakeSnapshot(null).Data);
            var epoch = snapshot.GetProperty("epoch").GetInt32();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                delete = new[] { "C1" },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("deleted").GetInt32());
            Assert.Contains("RemoveObject mutator unavailable", data.GetProperty("edit_summary").GetProperty("errors")[0].GetString());
            Assert.Single(document.Objects);
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_UnavailableCreatePrimitiveDoesNotManufactureCommit()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch = 0,
                create = new[] { new { temp_id = "T1", name = "Unavailable" } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("created").GetInt32());
            Assert.NotEqual(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Theory]
        [InlineData(
            "{\"epoch\":0,\"create\":[{\"temp_id\":\"TActorSetControl\",\"type\":\"slider\"}],\"connect\":[\"N1.O0>TActorSetControl.I0\"]}",
            "/connect/0",
            "invalid_component_reference",
            "N1")]
        [InlineData(
            "{\"epoch\":0,\"create\":[{\"temp_id\":\"T_CLEAN\",\"type\":\"slider\"},{\"temp_id\":\"T_CLEAN\",\"type\":\"panel\"}]}",
            "/create/1/temp_id",
            "duplicate_temp_id",
            "T_CLEAN")]
        [InlineData(
            "{\"epoch\":0,\"set_values\":[{\"id\":\"TABSENT\",\"value\":2}]}",
            "/set_values/0/id",
            "unresolved_temp_reference",
            "TABSENT")]
        [InlineData(
            "{\"epoch\":0,\"groups\":[{\"action\":\"create\",\"members\":[\"N2\"]}]}",
            "/groups/0/members/0",
            "invalid_component_reference",
            "N2")]
        [InlineData(
            "{\"epoch\":0,\"connect\":[\"C1.O\\u00A01>C2.I0\"]}",
            "/connect/0",
            "invalid_flow",
            "C1.O\u00A01>C2.I0")]
        [InlineData(
            "{\"epoch\":0,\"connect\":[\"C1.O\\u00851>C2.I0\"]}",
            "/connect/0",
            "invalid_flow",
            "C1.O\u00851>C2.I0")]
        public void ApplyEdit_InvalidReferencesRefuseBeforeGrasshopperAccessOrMutation(
            string body,
            string expectedPath,
            string expectedCode,
            string expectedValue)
        {
            var core = new ReadyCore();
            var document = new FakeDocument { ThrowOnObjectsRead = true };
            var handler = CreateHandler(document, bridgeCore: core);

            var response = handler.ApplyEdit(body);

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal(
                new[] { "error", "issues" },
                data.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal("gh_edit_admission_failed", data.GetProperty("error").GetString());
            var issue = Assert.Single(data.GetProperty("issues").EnumerateArray());
            Assert.Equal(
                new[] { "path", "code", "value" },
                issue.EnumerateObject().Select(property => property.Name).ToArray());
            Assert.Equal(expectedPath, issue.GetProperty("path").GetString());
            Assert.Equal(expectedCode, issue.GetProperty("code").GetString());
            Assert.Equal(expectedValue, issue.GetProperty("value").GetString());
            Assert.Equal(0, core.StatusCallCount);
            Assert.Equal(0, document.ObjectsReadCount);
            Assert.Equal(0, document.ScheduleCount);
            Assert.Empty(document.ObjectsWithoutObservation);
        }

        [Fact]
        public void ApplyEdit_AdmissionCollectsAllIssuesInClosedSemanticOrder()
        {
            const string body = "{\"epoch\":0,\"create\":[{\"temp_id\":\"T_OK\",\"type\":\"slider\"},{\"temp_id\":\"T_OK\",\"type\":\"panel\"},{\"temp_id\":\"N1\",\"type\":\"panel\"}],\"disconnect\":[\"TABSENT.O0>C1.I0\"],\"set_values\":[{\"id\":\"N3\",\"value\":2}],\"connect\":[\"bad\"],\"groups\":[{\"action\":\"create\",\"members\":[\"TABSENT\",\"N4\"]}]}";
            var core = new ReadyCore();
            var document = new FakeDocument { ThrowOnObjectsRead = true };
            var handler = CreateHandler(document, bridgeCore: core);

            var response = handler.ApplyEdit(body);

            Assert.False(response.Success);
            var issues = Element(response.Data).GetProperty("issues").EnumerateArray().ToArray();
            Assert.Equal(
                new[]
                {
                    ("/create/1/temp_id", "duplicate_temp_id", "T_OK"),
                    ("/create/2/temp_id", "invalid_temp_id", "N1"),
                    ("/disconnect/0", "unresolved_temp_reference", "TABSENT"),
                    ("/set_values/0/id", "invalid_component_reference", "N3"),
                    ("/connect/0", "invalid_flow", "bad"),
                    ("/groups/0/members/0", "unresolved_temp_reference", "TABSENT"),
                    ("/groups/0/members/1", "invalid_component_reference", "N4"),
                },
                issues.Select(issue => (
                    issue.GetProperty("path").GetString()!,
                    issue.GetProperty("code").GetString()!,
                    issue.GetProperty("value").GetString()!)).ToArray());
            Assert.Equal(0, core.StatusCallCount);
            Assert.Equal(0, document.ObjectsReadCount);
            Assert.Equal(0, document.ScheduleCount);
            Assert.Empty(document.ObjectsWithoutObservation);
        }

        [Fact]
        public void ApplyEdit_DescriptiveTempIdPreservesCorrelationAndReceipt()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch = 0,
                create = new[] { new { temp_id = "TActorSetControl", type = "slider" } },
                set_values = new[] { new { id = "TActorSetControl", value = 3m } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            var summary = data.GetProperty("edit_summary");
            Assert.Equal(1, summary.GetProperty("created").GetInt32());
            Assert.True(summary.GetProperty("temp_id_map").TryGetProperty("TActorSetControl", out _));
            Assert.True(summary.GetProperty("instance_guids").TryGetProperty("TActorSetControl", out _));
            var errors = summary.GetProperty("errors");
            if (errors.ValueKind == JsonValueKind.Array)
            {
                Assert.DoesNotContain(
                    errors.EnumerateArray().Select(error => error.GetString()),
                    error => error?.Contains("unknown ID") == true);
            }
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Single(document.Objects);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_SuccessfulCreateCountsConfirmedAddAndReturnsReceipt()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch = 0,
                create = new[] { new { temp_id = "T1", type = "slider" } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(1, data.GetProperty("edit_summary").GetProperty("created").GetInt32());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Equal("pending", data.GetProperty("solve_readiness_receipt").GetProperty("status").GetString());
            Assert.Single(document.Objects);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_CreateFalseReturnDoesNotManufactureCommit()
        {
            var document = new FakeDocument { AddResult = false };
            var handler = CreateHandler(document);

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch = 0,
                create = new[] { new { temp_id = "T1", type = "slider" } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(0, data.GetProperty("edit_summary").GetProperty("created").GetInt32());
            Assert.NotEqual(JsonValueKind.Null, data.GetProperty("edit_summary").GetProperty("errors").ValueKind);
            Assert.Empty(document.Objects);
            Assert.Equal(
                "no_solve_relevant_mutation_committed",
                data.GetProperty("solve_readiness_receipt").GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_MutatingGroupDeleteOmitsReceipt()
        {
            var group = new GH_Group(Guid.NewGuid());
            var document = new FakeDocument(group);
            var handler = CreateHandler(document);
            var snapshot = Element(handler.TakeSnapshot(null).Data);
            var epoch = snapshot.GetProperty("epoch").GetInt32();
            var groupId = snapshot.GetProperty("components")[0].GetProperty("id").GetString();

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                groups = new[] { new { action = "delete", id = groupId } },
            }));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Empty(document.Objects);
            Assert.False(data.TryGetProperty("solve_readiness_receipt", out _));
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ApplyEdit_GroupOnlySnapshotFailureWrapperOmitsReceipt()
        {
            var group = new GH_Group(Guid.NewGuid());
            var document = new FakeDocument(group);
            var handler = CreateHandler(document);
            var snapshot = Element(handler.TakeSnapshot(null).Data);
            var epoch = snapshot.GetProperty("epoch").GetInt32();
            var groupId = snapshot.GetProperty("components")[0].GetProperty("id").GetString();
            document.ThrowOnObjectsReadAt = document.ObjectsReadCount + 2;

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                groups = new[] { new { action = "delete", id = groupId } },
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Empty(document.ObjectsWithoutObservation);
            Assert.True(data.TryGetProperty("snapshot_failure", out _));
            Assert.False(data.TryGetProperty("solve_readiness_receipt", out _));
        }

        [Fact]
        public void ApplyEdit_GroupOnlyOuterFailureOmitsReceipt()
        {
            var group = new GH_Group(Guid.NewGuid());
            var document = new FakeDocument(group);
            var handler = CreateHandler(document);
            var snapshot = Element(handler.TakeSnapshot(null).Data);
            var epoch = snapshot.GetProperty("epoch").GetInt32();
            var groupId = snapshot.GetProperty("components")[0].GetProperty("id").GetString();
            ((FakeCanvas)ActiveCanvasProperty.GetValue(null)!).ThrowOnRefresh = true;

            var response = handler.ApplyEdit(JsonSerializer.Serialize(new
            {
                epoch,
                groups = new[] { new { action = "delete", id = groupId } },
            }));

            Assert.False(response.Success);
            var data = Element(response.Data);
            Assert.Equal("apply_edit_failed", data.GetProperty("error").GetString());
            Assert.Empty(document.ObjectsWithoutObservation);
            Assert.False(data.TryGetProperty("solve_readiness_receipt", out _));
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
                    new { id = "C999", value = 9m },
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
            object document,
            bool globalSolutionsEnabled = true,
            GhSolveReceiptRegistry? registry = null,
            bool throwOnRefresh = false,
            ReadyCore? bridgeCore = null)
        {
            FakeDocument.EnableSolutions = globalSolutionsEnabled;
            ActiveCanvasProperty.SetValue(null, new FakeCanvas(document) { ThrowOnRefresh = throwOnRefresh });
            return new GrasshopperHandler(
                bridgeCore: bridgeCore ?? new ReadyCore(),
                runningAsRhinoInside: () => false,
                solveReceiptRegistry: registry ?? new GhSolveReceiptRegistry(),
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
                var grasshopperAssembly = existing.DeclaringType!.Assembly;
                var existingModule = (grasshopperAssembly as AssemblyBuilder)?.GetDynamicModule("Grasshopper");
                if (existingModule != null)
                {
                    var paramInterface = grasshopperAssembly.GetType("Grasshopper.Kernel.IGH_Param");
                    if (paramInterface is null)
                    {
                        DefineGrasshopperParamTypes(existingModule);
                    }
                    else if (grasshopperAssembly.GetType("Grasshopper.Tests.ReceiptParam") is null)
                    {
                        DefineGrasshopperReceiptParam(existingModule, paramInterface);
                    }
                    if (grasshopperAssembly.GetType("Grasshopper.Kernel.Special.GH_NumberSlider") is null)
                    {
                        DefineGrasshopperNumberSlider(existingModule);
                    }
                }
                return existing;
            }

            var assembly = AppDomain.CurrentDomain.DefineDynamicAssembly(
                new AssemblyName("Grasshopper"),
                AssemblyBuilderAccess.Run);
            var module = assembly.DefineDynamicModule("Grasshopper");
            DefineGrasshopperParamTypes(module);
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

        private static void DefineGrasshopperParamTypes(ModuleBuilder module)
        {
            var paramInterface = module.DefineType(
                "Grasshopper.Kernel.IGH_Param",
                TypeAttributes.Public | TypeAttributes.Interface | TypeAttributes.Abstract)
                .CreateType()!;
            DefineGrasshopperReceiptParam(module, paramInterface);
            DefineGrasshopperNumberSlider(module);
        }

        private static Type DefineGrasshopperNumberSlider(ModuleBuilder module)
        {
            var type = module.DefineType(
                "Grasshopper.Kernel.Special.GH_NumberSlider",
                TypeAttributes.Public | TypeAttributes.Class);
            var guidField = type.DefineField("_instanceGuid", typeof(Guid), FieldAttributes.Private);
            var nickField = type.DefineField("_nickName", typeof(string), FieldAttributes.Private);
            var constructor = type.DefineConstructor(
                MethodAttributes.Public,
                CallingConventions.Standard,
                Type.EmptyTypes);
            var constructorIl = constructor.GetILGenerator();
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Call, typeof(Guid).GetMethod(nameof(Guid.NewGuid), BindingFlags.Public | BindingFlags.Static)!);
            constructorIl.Emit(OpCodes.Stfld, guidField);
            constructorIl.Emit(OpCodes.Ret);
            DefineReadOnlyProperty(type, "InstanceGuid", typeof(Guid), guidField);
            DefineReadWriteProperty(type, "NickName", typeof(string), nickField);
            DefineNullProperty(type, "Slider");
            var expire = type.DefineMethod("ExpireSolution", MethodAttributes.Public, typeof(void), new[] { typeof(bool) });
            expire.GetILGenerator().Emit(OpCodes.Ret);
            return type.CreateType()!;
        }

        private static Type DefineGrasshopperReceiptParam(ModuleBuilder module, Type paramInterface)
        {
            var type = module.DefineType(
                "Grasshopper.Tests.ReceiptParam",
                TypeAttributes.Public | TypeAttributes.Class);
            type.AddInterfaceImplementation(paramInterface);

            var guidField = type.DefineField("_instanceGuid", typeof(Guid), FieldAttributes.Private);
            var addCallsField = type.DefineField("_addCalls", typeof(int), FieldAttributes.Private);
            var removeCallsField = type.DefineField("_removeCalls", typeof(int), FieldAttributes.Private);
            var constructor = type.DefineConstructor(
                MethodAttributes.Public,
                CallingConventions.Standard,
                new[] { typeof(Guid) });
            var constructorIl = constructor.GetILGenerator();
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Ldarg_1);
            constructorIl.Emit(OpCodes.Stfld, guidField);
            constructorIl.Emit(OpCodes.Ret);

            DefineReadOnlyProperty(type, "InstanceGuid", typeof(Guid), guidField);
            DefineReadOnlyProperty(type, "AddCalls", typeof(int), addCallsField);
            DefineReadOnlyProperty(type, "RemoveCalls", typeof(int), removeCallsField);
            DefineNullProperty(type, "Sources");
            DefineNullProperty(type, "Recipients");
            DefineCountingMethod(type, "AddSource", paramInterface, addCallsField);
            DefineCountingMethod(type, "RemoveSource", paramInterface, removeCallsField);
            var expire = type.DefineMethod("ExpireSolution", MethodAttributes.Public, typeof(void), new[] { typeof(bool) });
            var expireIl = expire.GetILGenerator();
            expireIl.Emit(OpCodes.Ret);
            return type.CreateType()!;
        }

        private static void DefineReadOnlyProperty(
            TypeBuilder type,
            string name,
            Type propertyType,
            FieldBuilder field)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, propertyType, Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                propertyType,
                Type.EmptyTypes);
            var il = getter.GetILGenerator();
            il.Emit(OpCodes.Ldarg_0);
            il.Emit(OpCodes.Ldfld, field);
            il.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
        }

        private static void DefineNullProperty(TypeBuilder type, string name)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, typeof(object), Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(object),
                Type.EmptyTypes);
            var il = getter.GetILGenerator();
            il.Emit(OpCodes.Ldnull);
            il.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
        }

        private static void DefineReadWriteProperty(
            TypeBuilder type,
            string name,
            Type propertyType,
            FieldBuilder field)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, propertyType, Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                propertyType,
                Type.EmptyTypes);
            var getterIl = getter.GetILGenerator();
            getterIl.Emit(OpCodes.Ldarg_0);
            getterIl.Emit(OpCodes.Ldfld, field);
            getterIl.Emit(OpCodes.Ret);
            var setter = type.DefineMethod(
                $"set_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(void),
                new[] { propertyType });
            var setterIl = setter.GetILGenerator();
            setterIl.Emit(OpCodes.Ldarg_0);
            setterIl.Emit(OpCodes.Ldarg_1);
            setterIl.Emit(OpCodes.Stfld, field);
            setterIl.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
            property.SetSetMethod(setter);
        }

        private static void DefineCountingMethod(
            TypeBuilder type,
            string name,
            Type paramInterface,
            FieldBuilder counter)
        {
            var method = type.DefineMethod(name, MethodAttributes.Public, typeof(void), new[] { paramInterface });
            var il = method.GetILGenerator();
            il.Emit(OpCodes.Ldarg_0);
            il.Emit(OpCodes.Ldarg_0);
            il.Emit(OpCodes.Ldfld, counter);
            il.Emit(OpCodes.Ldc_I4_1);
            il.Emit(OpCodes.Add);
            il.Emit(OpCodes.Stfld, counter);
            il.Emit(OpCodes.Ret);
        }

        private static object CreateDynamicParam(Guid guid)
        {
            var grasshopperAssembly = AppDomain.CurrentDomain.GetAssemblies()
                .Single(assembly => assembly.GetName().Name == "Grasshopper");
            var type = grasshopperAssembly.GetType("Grasshopper.Tests.ReceiptParam");
            if (type is null)
            {
                var paramInterface = grasshopperAssembly.GetType("Grasshopper.Kernel.IGH_Param")
                    ?? throw new InvalidOperationException("Grasshopper.Kernel.IGH_Param test type is unavailable");
                var assembly = AppDomain.CurrentDomain.DefineDynamicAssembly(
                    new AssemblyName($"Rook.Tests.ReceiptParam.{Guid.NewGuid():N}"),
                    AssemblyBuilderAccess.Run);
                type = DefineGrasshopperReceiptParam(
                    assembly.DefineDynamicModule("ReceiptParam"),
                    paramInterface);
            }
            return Activator.CreateInstance(type, guid)!;
        }

        private static int GetDynamicParamCount(object param, string propertyName) =>
            (int)param.GetType().GetProperty(propertyName)!.GetValue(param)!;

        private sealed class ReadyCore : IGrasshopperCore
        {
            public int StatusCallCount { get; private set; }

            public BridgeResult<GrasshopperStatusDto> GetStatus()
            {
                StatusCallCount++;
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
            public bool ThrowOnRefresh { get; set; }
            public event EventHandler<FakeCanvasDocumentChangedEventArgs>? DocumentChanged;

            public void Refresh()
            {
                if (ThrowOnRefresh)
                    throw new InvalidOperationException("refresh failed after group mutation");
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

        public sealed class FakeSolutionEventArgs : EventArgs
        {
            public FakeSolutionEventArgs(object document) => Document = document;
            public object Document { get; }
        }

        public sealed class FakeDocument
        {
            private readonly List<object> _objects;

            public FakeDocument(params object[] objects) => _objects = objects.ToList();

            public static bool EnableSolutions { get; set; } = true;
            public Guid DocumentID { get; } = Guid.NewGuid();
            public bool Enabled { get; set; } = true;
            public bool ThrowOnObjectsRead { get; set; }
            public int? ThrowOnObjectsReadAt { get; set; }
            public int ObjectsReadCount { get; private set; }
            public IReadOnlyList<object> Objects
            {
                get
                {
                    ObjectsReadCount++;
                    if (ThrowOnObjectsRead)
                    {
                        throw new InvalidOperationException("objects unavailable before reservation");
                    }
                    if (ThrowOnObjectsReadAt == ObjectsReadCount)
                    {
                        throw new InvalidOperationException("objects unavailable during structural snapshot");
                    }

                    return _objects;
                }
            }
            public IReadOnlyList<object> ObjectsWithoutObservation => _objects;
            public int ScheduleCount { get; private set; }
            public bool ThrowOnSchedule { get; set; }
            public bool AddResult { get; set; } = true;
            public bool RemoveResult { get; set; } = true;
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

            public bool RemoveObject(FakeAttributes attributes, bool update)
            {
                if (RemoveResult)
                    _objects.Remove(attributes.Owner);
                return RemoveResult;
            }

            public bool AddObject(object component, bool update)
            {
                if (AddResult)
                    _objects.Add(component);
                return AddResult;
            }
        }

        public sealed class FakeDocumentWithoutRemove
        {
            public FakeDocumentWithoutRemove(params object[] objects) => Objects = objects.ToList();
            public bool Enabled { get; set; } = true;
            public IReadOnlyList<object> Objects { get; }
            public int ScheduleCount { get; private set; }
            public FakeUndoUtil UndoUtil { get; } = new();
            public event EventHandler<FakeSolutionEventArgs>? SolutionStart;
            public event EventHandler<FakeSolutionEventArgs>? SolutionEnd;
            public void ScheduleSolution(int delayMs) => ScheduleCount++;
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

        public sealed class FakeAttributes
        {
            public FakeAttributes(object owner) => Owner = owner;
            public object Owner { get; }
        }

        public sealed class FakeDeletableComponent
        {
            public FakeDeletableComponent(Guid instanceGuid)
            {
                InstanceGuid = instanceGuid;
                Attributes = new FakeAttributes(this);
            }

            public Guid InstanceGuid { get; }
            public FakeAttributes Attributes { get; }
            public void ExpireSolution(bool recompute) { }
        }

        public sealed class FakeSimpleParam
        {
            public FakeSimpleParam(Guid instanceGuid) => InstanceGuid = instanceGuid;
            public Guid InstanceGuid { get; }
            public object? Sources => null;
            public object? Recipients => null;
            public void ExpireSolution(bool recompute) { }
        }

        public sealed class GH_Group
        {
            public GH_Group(Guid instanceGuid)
            {
                InstanceGuid = instanceGuid;
                Attributes = new FakeAttributes(this);
            }

            public Guid InstanceGuid { get; }
            public string NickName { get; set; } = "Group";
            public string Description { get; set; } = string.Empty;
            public FakeAttributes Attributes { get; }
            public IEnumerable<Guid> ObjectIDs() => Array.Empty<Guid>();
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
            public bool ThrowOnSetSource { get; set; }

            public void SetSource(string source)
            {
                if (ThrowOnSetSource)
                {
                    throw new InvalidOperationException("source mutation failed");
                }

                Source = source;
            }

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

        public sealed class FakeLegacyScriptComponent
        {
            public FakeLegacyScriptComponent(Guid instanceGuid) => InstanceGuid = instanceGuid;
            public Guid InstanceGuid { get; }
            public object? ScriptSource => null;
        }
    }
}

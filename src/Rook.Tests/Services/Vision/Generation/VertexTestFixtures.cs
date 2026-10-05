using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Image.Vertex;

namespace Rook.Tests.Services.Vision.Generation
{
    internal sealed class VertexTestTokenSource : IVertexAccessTokenSource
    {
        public string Generation = "0123456789abcdef0123456789abcdef";
        public string Project = "company-project";
        public bool Workforce;
        public string PrincipalId = new string('b', 32);
        public string Fingerprint = new string('c', 64);
        public string? QuotaProject = "synthetic-firm-project";
        private VertexAuthorizationBinding Binding(string model, string location) => Workforce
            ? new(2, Generation, Project, location, model, PrincipalId, Fingerprint, "synthetic-user-project", QuotaProject)
            : new(1, Generation, Project, location, model);
        public VertexAccessTokenFailure? Failure;
        public Func<VertexAuthorizationBinding, CancellationToken, Task<VertexAccessTokenFailure?>>? OnValidate;
        public int AcquireCalls;
        public int ValidateCalls;
        public Task<VertexAccessTokenResult> AcquireAsync(string model, string location, VertexAuthorizationBinding? expected, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); AcquireCalls++;
            var binding = Binding(model, location);
            var failure = Failure ?? (expected is not null && expected != binding ? new VertexAccessTokenFailure("vertex_authorization_changed","Authorization changed.",false) : null);
            return Task.FromResult(failure is not null ? new VertexAccessTokenResult(null,failure) : new VertexAccessTokenResult(new VertexAccessTokenLease("secret-bearer-sentinel",DateTimeOffset.UtcNow.ToUnixTimeSeconds()+3600,Project,location,Generation,binding, Workforce ? 2 : 1, Workforce ? QuotaProject : null),null));
        }
        public Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding,CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); ValidateCalls++;
            return OnValidate?.Invoke(binding,ct) ?? Task.FromResult(Failure ?? (binding != Binding(binding.ModelId, binding.Location) ? new VertexAccessTokenFailure("vertex_authorization_changed","Authorization changed.",false) : null));
        }
    }
    internal sealed class VertexTestHandler : HttpMessageHandler
    {
        internal Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> Send;
        internal int Calls;
        internal VertexTestHandler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send) {Send=send;}
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct) {Calls++; return Send(request,ct);}
    }
}

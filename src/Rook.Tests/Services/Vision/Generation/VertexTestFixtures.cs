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
        public VertexAccessTokenFailure? Failure;
        public Func<VertexAuthorizationBinding, CancellationToken, Task<VertexAccessTokenFailure?>>? OnValidate;
        public int AcquireCalls;
        public int ValidateCalls;
        public Task<VertexAccessTokenResult> AcquireAsync(string model, string location, VertexAuthorizationBinding? expected, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); AcquireCalls++;
            var binding = new VertexAuthorizationBinding(1,Generation,Project,location,model);
            var failure = Failure ?? (expected is not null && expected != binding ? new VertexAccessTokenFailure("vertex_authorization_changed","Authorization changed.",false) : null);
            return Task.FromResult(failure is not null ? new VertexAccessTokenResult(null,failure) : new VertexAccessTokenResult(new VertexAccessTokenLease("secret-bearer-sentinel",DateTimeOffset.UtcNow.ToUnixTimeSeconds()+3600,Project,location,Generation,binding),null));
        }
        public Task<VertexAccessTokenFailure?> ValidateBindingAsync(VertexAuthorizationBinding binding,CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); ValidateCalls++;
            return OnValidate?.Invoke(binding,ct) ?? Task.FromResult(Failure ?? (binding.AuthorizationGeneration != Generation || binding.ProjectId != Project ? new VertexAccessTokenFailure("vertex_authorization_changed","Authorization changed.",false) : null));
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

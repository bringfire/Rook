# Local patches to the vendored cpp-httplib

Upstream: cpp-httplib 0.18.3 (MIT). Re-apply these when upgrading; each site
is marked `ROOK PATCH` in `httplib.h`.

## 1. `Server::routing`: drain a declared body after a pre-routing refusal

The Rook native server refuses non-Rook requests in a `set_pre_routing_handler`
gate (`src/RookNative/RookServer.cpp`), which upstream runs before the request
body is read. Two consequences the patch addresses:

- With keep-alive, the unread body of a refused POST would be parsed as the
  *next* request (request smuggling: a blind cross-origin POST from a web page
  can make its body a complete request that passes the gate). Rook closes this
  with `set_keep_alive_max_count(1)` in `RookServer.cpp`, not in this patch.
- With one request per connection, closing a socket that still holds unread
  data sends a TCP reset, and on Windows a reset discards data the client has
  not yet read, so the 403 could be lost. The patch consumes and discards a
  declared `Content-Length` body (up to 8 MiB, never chunked, never
  length-less) before returning, so the refusal is written and the socket
  closes with a normal FIN. The drained bytes are never parsed or dispatched.

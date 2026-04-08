// RequestContext.h
//
// Thread-local document pinning for HTTP request handlers.
// Replaces C#'s AsyncLocal<uint?> with thread_local + RAII scope guard.
//
// Usage:
//   void HandleRequest(const httplib::Request& req, httplib::Response& res) {
//       unsigned int doc_sn = ParseDocSerial(req.body);
//       CRequestScope scope(doc_sn);   // pins document for this request
//       // ... handler code sees g_request_doc_serial ...
//   }  // scope destructor restores previous value

#pragma once

// The document serial number for the current request on this thread.
// 0 means "use active document" (same semantics as C#'s null AsyncLocal).
inline thread_local unsigned int g_request_doc_serial = 0;

// RAII guard: sets the document serial on construction, restores on destruction.
// Supports nesting (saves/restores previous value).
class CRequestScope
{
public:
    explicit CRequestScope(unsigned int doc_serial)
        : m_previous(g_request_doc_serial)
    {
        g_request_doc_serial = doc_serial;
    }

    ~CRequestScope()
    {
        g_request_doc_serial = m_previous;
    }

    CRequestScope(const CRequestScope&) = delete;
    CRequestScope& operator=(const CRequestScope&) = delete;

private:
    unsigned int m_previous;
};

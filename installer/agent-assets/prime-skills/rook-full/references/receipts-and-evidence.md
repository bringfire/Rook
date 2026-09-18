# Receipts And Evidence

Parse every Rook result envelope. A `success: false` envelope is authoritative
failure information and must not be treated as success because transport
completed.

For mutations:

1. Preserve every authentic unique receipt returned by a committed operation.
2. Never replay an operation whose outcome is ambiguous.
3. Wait for solve or readiness using the receipt required by that operation.
4. Obtain the final same-receipt fenced observation before claiming the result.
5. Make no later Rook call if that observation is intended as final completion
   evidence.

A successful no-op does not earn a mutation receipt or prove that a requested
change occurred. When several authorized mutations are necessary, attribute each
receipt and use the last actual solve-relevant receipt that leaves the requested
final state in place.

Keep operation truth separate from prompt truth. An authentic Rook result and
receipt remain authoritative for that operation even if the enclosing ACP prompt
later fails. ACP settlement does not by itself certify a mutation or complete a
Prime goal.

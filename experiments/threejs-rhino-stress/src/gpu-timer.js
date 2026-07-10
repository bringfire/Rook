export function createGpuTimer(gl) {
  const extension = gl.getExtension("EXT_disjoint_timer_query_webgl2");
  const pending = [];
  const samplesMs = [];
  // Number of queued timing samples discarded after disjoint signals.
  let disjointCount = 0;
  let active = null;

  return {
    available: Boolean(extension),
    begin() {
      if (!extension || active) return;
      active = gl.createQuery();
      gl.beginQuery(extension.TIME_ELAPSED_EXT, active);
    },
    end() {
      if (!extension || !active) return;
      gl.endQuery(extension.TIME_ELAPSED_EXT);
      pending.push(active);
      active = null;
    },
    poll() {
      if (!extension) return;
      const disjoint = gl.getParameter(extension.GPU_DISJOINT_EXT);
      if (disjoint) {
        disjointCount += pending.length + samplesMs.length;
        pending.forEach((query) => gl.deleteQuery(query));
        pending.length = 0;
        samplesMs.length = 0;
        return;
      }
      for (let index = pending.length - 1; index >= 0; index -= 1) {
        const query = pending[index];
        if (!gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE)) continue;
        const nanoseconds = gl.getQueryParameter(query, gl.QUERY_RESULT);
        samplesMs.push(nanoseconds / 1000000);
        gl.deleteQuery(query);
        pending.splice(index, 1);
      }
    },
    snapshot: () => ({
      available: Boolean(extension),
      samplesMs: [...samplesMs],
      disjointCount,
      pendingCount: pending.length,
    }),
    dispose() {
      if (active) gl.deleteQuery(active);
      pending.forEach((query) => gl.deleteQuery(query));
      pending.length = 0;
      active = null;
    },
  };
}

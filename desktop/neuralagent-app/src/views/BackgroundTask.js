import React from 'react';

export default function BackgroundTask() {
  return (
    <div style={{ height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <iframe
        src="http://127.0.0.1:39742/vnc.html?autoconnect=true&view_only=true&bell=off"
        style={{ width: '100%', height: '100%', border: 'none' }}
        title="NeuralAgent Background"
      />
    </div>
  );
}

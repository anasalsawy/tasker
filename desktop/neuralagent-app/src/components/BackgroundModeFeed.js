import { useEffect, useRef } from "react";

export default function BackgroundModeFeed() {
  const ref = useRef(null);

  useEffect(() => {
    const socket = new WebSocket("ws://127.0.0.1:27673");
    socket.onmessage = (event) => {
      if (ref.current) {
        ref.current.src = "data:image/jpeg;base64," + event.data;
      }
    };

    return () => socket.close();
  }, []);

  return (
    <img
      ref={ref}
      style={{ width: "100%", maxWidth: 800, borderRadius: 8 }}
      alt="Live Agent View"
    />
  );
}

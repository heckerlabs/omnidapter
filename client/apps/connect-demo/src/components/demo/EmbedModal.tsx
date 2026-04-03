import React from "react";

interface EmbedModalProps {
  src: string;
  onClose: () => void;
  styles: Record<string, React.CSSProperties>;
}

export function EmbedModal({ src, onClose, styles }: EmbedModalProps) {
  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.modalHeader}>
          <span style={styles.modalTitle}>Connect</span>
          <button style={styles.modalClose} onClick={onClose}>
            ✕
          </button>
        </div>
        <iframe src={src} style={styles.iframe} title="Omnidapter Connect" />
      </div>
    </div>
  );
}

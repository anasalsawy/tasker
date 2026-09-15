import React from 'react';
import ClipLoader from "react-spinners/ClipLoader";

function FullLoading() {
  return (
    <div style={{height: '100%', zIndex: '2000', position: 'fixed', 
      width: '100%', background: 'var(--primary-color)', display: 'flex', alignItems: 'center',
      justifyContent: 'center', top: '0', bottom: '0', left: '0', right: '0'}}>
        <ClipLoader
          color="#fff"
          size={150}
        />
    </div>
  );
}

export default FullLoading;
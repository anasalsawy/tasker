import React, { useEffect, useState } from 'react';
import styled from 'styled-components';

const Wrapper = styled.div`
  padding: 30px;
  color: white;
  text-align: center;
`;

const ProgressBar = styled.div`
  height: 10px;
  width: 100%;
  background: rgba(255,255,255,0.1);
  border-radius: 8px;
  margin-top: 20px;
`;

const Fill = styled.div`
  height: 100%;
  width: ${props => props.pct}%;
  background: #4BB543;
  border-radius: 8px;
  transition: width 0.3s ease;
`;

export default function BackgroundSetup() {
  const [status, setStatus] = useState('Working...');
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    window.electronAPI.onSetupStatus(setStatus);
    window.electronAPI.onSetupProgress(setProgress);
    window.electronAPI.onSetupComplete(result => {
      if (result.success) {
        setStatus('Setup Complete! You can now use Background Mode.');
        setTimeout(() => window.close(), 4000);
      } else {
        setStatus(`${result.error || 'Setup Failed: Please ensure you have Windows 10 or higher and that virtualization is enabled in BIOS.'}`);
      }
    });
    window.electronAPI.startBackgroundSetup();
  }, []);

  return (
    <Wrapper>
      <div style={{fontSize: '18px', fontWeight: '600'}}>Setting up Background Mode</div>
      <p style={{fontSize: '16px', fontWeight: '400'}}>{status}</p>
      <ProgressBar>
        <Fill pct={progress} />
      </ProgressBar>
    </Wrapper>
  );
}

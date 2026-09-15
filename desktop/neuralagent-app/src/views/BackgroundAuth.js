import React from 'react';
import styled from 'styled-components';

const Container = styled.div`
  display: flex;
  flex-direction: column;
  color: var(--secondary-color);
  height: 100vh;
  width: 100vw;
  overflow: hidden;
`;

const InstructionBox = styled.div`
  padding: 1rem 2rem;
  font-size: 1rem;
  line-height: 1.6;
  text-align: center;
  border-bottom: 1px solid var(--third-color);
`;

const Highlight = styled.span`
  font-weight: 500;
  color: var(--light-gray-background);
`;

const FrameWrapper = styled.div`
  flex: 1;
  iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
`;

export default function BackgroundAuth() {
  return (
    <Container>
      <InstructionBox>
        Log in to any sites or apps you'd like <Highlight>NeuralAgent</Highlight> to control in the background. Close the window when you finish.<br />
        <small style={{ opacity: 0.7 }}>
          These sessions are stored securely on your computer. You can always do this from App &gt; Background Mode Authentication.
        </small>
      </InstructionBox>
      <FrameWrapper>
        <iframe
          src="http://127.0.0.1:39742/vnc.html?autoconnect=true&bell=off"
          title="NeuralAgent VNC Session"
        />
      </FrameWrapper>
    </Container>
  );
}

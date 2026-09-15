import styled from 'styled-components';

export const LoadingDialogContainer = styled.div`
  position: fixed;
  z-index: 1500;
  height: 200px;
  width: 200px;
  background: var(--card-color);
  display: flex;
  justify-content: center;
  align-items: center;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  border-radius: 10px;
  box-shadow: 0 19px 38px rgba(0,0,0,0.30), 0 15px 12px rgba(0,0,0,0.22);

  :before {
    background-color: red;
  }
`

export const LoadingDialogOverlay = styled.div`
  position: fixed;
  z-index: 1000;
  height: 100%;
  width: 100%;
  background-color: rgba(0, 0, 0, 0.6);
  left: 0%;
  top: 0%;
`

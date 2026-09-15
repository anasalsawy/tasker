import styled from 'styled-components';

export const DialogContainer = styled.div`
  position: fixed;
  z-index: 1000;
  width: 90%;
  max-width: ${props => props.maxWidth ? props.maxWidth : '500px'};
  background: ${props => props.isDarkMode ? 'var(--dark-theme-background)' : '#fff'};
  justify-content: center;
  align-items: center;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  border-radius: 10px;
  box-shadow: 0 19px 38px rgba(0,0,0,0.30), 0 15px 12px rgba(0,0,0,0.22);
  max-height: 100vh;
`

export const DialogOverlay = styled.div`
  position: fixed;
  z-index: 1000;
  height: 100%;
  width: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  left: 0%;
  top: 0%;
`

export const DialogHeader = styled.div`
  display: flex;
  align-items: center;
  padding: 15px 20px;
`

export const HeaderEnd = styled.div`
  margin-left: ${props => props.isRTL ? '0px' : 'auto'};
  margin-right: ${props => props.isRTL ? 'auto' : '0px'};
`

export const DialogTitle = styled.div`
  font-size: 17px;
  color: ${props => props.isDarkMode ? '#fff' : '#000'};
  font-weight: 700;
`

export const DialogContent = styled.div`
  padding: ${props => props.padding ? props.padding : '10px'};
  display: flex;
  flex-direction: column;
  overflow: ${props => props.scrollable ? 'auto' : 'unset'};
  height: ${props => props.scrollable ? (props.height ? props.height : '500px') : 'unset'};
`

export const DialogActions = styled.div`
  display: flex;
  align-items: center;
  padding: 10px;
`

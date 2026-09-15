import styled from 'styled-components';

export const MessageBarContainer = styled.div`
  position: fixed;
  top: 80px;
  z-index: 2000;
  padding: 20px 50px;
  background-color: ${props => props.backgroundColor ? props.backgroundColor : 'green'};
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  color: #fff;
  font-weight: 500;
  border-radius: 6px;
  box-shadow: 0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23);
  transition: 0.2s ease-in-out;
  max-width: 700px;
  display: flex;
  justify-content: center;
  align-items: center;
`

import styled from 'styled-components';

export const TabsContainer = styled.div`
  display: flex;
  align-items: center;
  overflow: auto;
  padding-left: 0;
  width: 100%;

  &::-webkit-scrollbar {
    display: none;
  }
`

export const Tab = styled.div`
  cursor: pointer;
  user-select: none;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 16px;
  font-weight: 500;
  width: 100%;
  color: ${props => props.isDarkMode ? '#fff' : 'var(--primary-color)'};

  &:hover {
    background: ${props => props.isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'};
    font-weight: 600;
    border-bottom: 3px solid ${props => props.isDarkMode ? '#fff' : 'var(--primary-color)'};
  }

  &.active {
    font-weight: 600;
    border-bottom: 3px solid ${props => props.isDarkMode ? '#fff' : 'var(--primary-color)'};
  }
`

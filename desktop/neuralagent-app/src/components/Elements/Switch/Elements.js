import styled from 'styled-components';

export const SwitchContainer = styled.div`
  display: flex;
  flex-direction: row;
  align-items: center;
  cursor: pointer;
  user-select: none;
`

export const SwitchIcon = styled.div`
  color: ${props => props.color ? props.color : 'var(--primary-color)'};
  font-size: 40px;
  height: 45px;
`

export const SwitchTextContainer = styled.div`
  padding: 0px 7px;
`

export const SwitchTitle = styled.div`
  font-size: 16px;
  font-weight: 500;
  color: ${props => props.color ? props.color : '#000'};
`

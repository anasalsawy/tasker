import styled from 'styled-components';

export const CheckboxContainer = styled.div`
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
`

export const CheckboxIcon = styled.div`
  color: ${props => props.color ? props.color : 'var(--primary-color)'};
  font-size: 26px;
  height: 26px;
`

export const CheckboxTextContainer = styled.div`
  padding: 0px 7px;
`

export const CheckboxTitle = styled.div`
  font-size: 18px;
  font-weight: 400;
  color: ${props => props.color ? props.color : 'var(--primary-color)'};
`

export const CheckboxHint = styled.div`
  margin-top: -7px;
  font-size: 14px;
  font-weight: 300;
  color: rgba(0, 0, 0, 0.5);
`

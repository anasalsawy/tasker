import styled from 'styled-components';

export const Text = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  color: ${props => props.color ? props.color : '#000'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '400'};
  text-align: ${props => props.textAlign ? props.textAlign : 'unset'};
`

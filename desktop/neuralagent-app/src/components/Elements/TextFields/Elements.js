import styled from 'styled-components';
import breakpoint from '../../../utils/breakpoint';

export const LabeledTFContainer = styled.div`
  display: flex;
  align-items: center;

  @media screen and (${breakpoint.devices_max.xs}) {
    align-items: stretch;
    flex-direction: column;
  }
`

export const VerticalLabeledTFContainer = styled.div`
  display: flex;
  flex-direction: column;
`

export const TextFieldLabel = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '500'};
  color: ${props => props.isDarkMode ? '#fff' : '#000'};
  padding-right: 15px;
  flex: 1 1 25%;
  margin-bottom: ${props => props.verticalLabel ? '7px' : '0px'};

  @media screen and (${breakpoint.devices_max.xs}) {
    padding-right: 0px;
    margin-bottom: 7px;
  }
`

export const TextField = styled.input`
  background: ${props => props.background ? props.background : '#fff'};
  padding: ${props => props.padding ? props.padding : '12px 15px'};
  color: ${props => props.isDarkMode ? '#fff' : '#000'};
  width: 100%;
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  border-radius: ${props => props.borderRadius ? props.borderRadius : '7px'};
  font-family: inherit;
  resize: none;
  outline: ${props => props.outlined ? 'rgba(0, 0, 0, 0.9) solid 1px' : 'none'};
  border: none;
  font-weight: 400;

  &::placeholder {
    color: ${props => props.isDarkMode ? 'rgba(255, 255, 255, 0.6)' : 'rgba(0, 0, 0, 0.6)'};
    font-size: ${props => props.fontSize ? props.fontSize : '16px'};
    font-weight: 500;
  }

  &:focus {
    outline: ${props => props.outlined ? 'var(--primary-color) solid 2px' : 'none'};
  }
`

export const TextFieldError = styled.div`
  margin-top: 2px;
  color: var(--danger-color);
  font-size: 16px;
`

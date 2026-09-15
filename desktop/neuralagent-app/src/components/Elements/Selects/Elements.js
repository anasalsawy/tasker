import styled from 'styled-components';
import breakpoint from '../../../utils/breakpoint';

export const LabeledSelectContainer = styled.div`
  display: flex;
  align-items: center;

  @media screen and (${breakpoint.devices_max.xs}) {
    align-items: stretch;
    flex-direction: column;
  }
`

export const VerticalLabeledSelectContainer = styled.div`
  display: flex;
  flex-direction: column;
`

export const SelectLabel = styled.div`
  font-size: 16px;
  font-weight: 500;
  color: #000;
  padding-right: 15px;
  flex: 1 1 25%;
  margin-bottom: ${props => props.verticalLabel ? '7px' : '0px'};

  @media screen and (${breakpoint.devices_max.xs}) {
    padding-right: 0px;
    margin-bottom: 7px;
  }
`

export const Select = styled.div`
  background: ${props => props.background ? props.background : '#fff'};
  padding: ${props => props.padding ? props.padding : '10px 8px'};
  position: relative;
  width: 100%;
  border-radius: ${props => props.borderRadius ? props.borderRadius : '7px'};
  font-family: inherit;
  resize: none;
  outline: ${props => props.outlined ? 'rgba(0, 0, 0, 0.9) solid 1px' : 'none'};
  border: none;
  display: flex;
  align-items: center;

  &:hover {
    outline: ${props => props.outlined ? 'var(--primary-color) solid 2px' : 'none'};
  }
`

export const SelectInput = styled.input`
  background: transparent;
  color: #000;
  font-size: 16px;
  font-family: inherit;
  flex-grow: 1;
  outline: none;
  border: none;

  &::placeholder {
    color: rgba(0, 0, 0, 0.6);
    font-size: 16px;
    font-weight: 500;
  }
`

export const OptionsDiv = styled.div`
  position: absolute;
  top: 40px;
  left: 0;
  width: 100%;
  z-index: 1;
  background: #fff;
  box-shadow: rgba(17, 12, 46, 0.15) 0px 48px 100px 0px;
`

export const OptionsDivContainer = styled.div`
  overflow: auto;
  max-height: 200px;
`

export const SelectError = styled.div`
  margin-top: 2px;
  color: var(--danger-color);
  font-size: 16px;
`

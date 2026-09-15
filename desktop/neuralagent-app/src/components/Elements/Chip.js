import styled from 'styled-components';

export const Chip = styled.div`
  border-radius: ${props => (props.borderRadius) ? '' + props.borderRadius + 'px' : '0px'};
  background: ${props => (props.color && !props.outlined) ? (props.color) : (props.outlined ? 'transparent' : 'var(--primary-color)')};
  padding: ${props => props.padding ? props.padding : '0px'};
  color: ${props => (props.outlined && props.color) ? props.color : (props.dark) ? '#fff' : '#000'};
  text-decoration: none;
  border: none;
  width: ${props => props.block ? '100%' : 'auto'};
  outline: ${props => (props.outlined) ? (props.color ? (props.color + ' 2px solid') : ('#000 2px solid')) : 'none'};
  box-shadow: ${props => (props.elevated ? '0 10px 20px rgba(0,0,0,0.19), 0 6px 6px rgba(0,0,0,0.23);' : 'none')};
  pointer-events: ${props => props.disabled ? 'none' : ''};
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '400'};
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  user-select: none;
`

export const ChipIcon = styled.div`
  font-size: ${props => props.iconSize ? props.iconSize : '23px'};
  height: ${props => props.iconSize ? props.iconSize : '23px'};
  color: ${props => props.color ? props.color : '#000'};
  padding-right: ${props => props.left ? '10px' : '0px'};
  padding-left: ${props => props.right ? '10px' : '0px'};
`

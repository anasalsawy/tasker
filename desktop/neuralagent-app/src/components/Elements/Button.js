import styled from 'styled-components';

export const Button = styled.button`
  border-radius: ${props => (props.borderRadius) ? '' + props.borderRadius + 'px' : '0px'};
  background: ${props => (props.color && !props.outlined) ? (props.color) : (props.outlined ? 'transparent' : 'var(--primary-color)')};
  padding: ${props => props.padding ? props.padding : '0px'};
  color: ${props => (props.outlined && props.color) ? props.color : (props.dark) ? '#fff' : '#000'};
  text-decoration: none;
  border: none;
  width: ${props => props.block ? '100%' : 'auto'};
  outline: ${props => (props.outlined) ? (props.color ? (props.color + ' 2px solid') : ('#000 2px solid')) : 'none'};
  box-shadow: ${props => (props.elevated ? '0 10px 20px rgba(0,0,0,0.19), 0 6px 6px rgba(0,0,0,0.23)' : 'none')};
  pointer-events: ${props => props.disabled ? 'none' : 'auto'};
  cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'};
  font-family: inherit;
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '500'};
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  user-select: none;
  opacity: ${props => props.disabled ? '0.5' : '1.0'};

  &:hover {
    opacity: ${props => props.disabled ? '0.5' : '0.8'};
  }
`

export const BtnIcon = styled.div`
  font-size: ${props => props.iconSize ? props.iconSize : '23px'};
  height: ${props => props.iconSize ? props.iconSize : '23px'};
  color: ${props => props.color ? props.color : '#000'};
  padding-right: ${props => props.left ? '10px' : '0px'};
  padding-left: ${props => props.right ? '10px' : '0px'};
  display: flex;
  align-items: center;
  justify-content: center;
`

export const IconButton = styled.div`
  font-size: ${props => props.iconSize ? props.iconSize : '23px'};
  height: ${props => props.iconSize ? props.iconSize : '23px'};
  color: ${props => props.color ? props.color : '#000'};
  cursor: pointer;
  border-radius: 50%;
  pointer-events: ${props => props.disabled ? 'none' : 'auto'};
  opacity: ${props => props.disabled ? '0.5' : '1.0'};
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
`

export const AvatarButton = styled.div`
  width: ${props => props.size ? props.size : '50px'};
  height: ${props => props.size ? props.size : '50px'};
  background: ${props => props.color ? props.color : 'var(--primary-color)'};
  box-shadow: ${props => props.raised ? '0 4pt 8pt rgb(0 0 0 / 20%)' : 'none'};
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;

  &:hover {
    opacity: ${props => props.disabled ? '0.5' : '0.8'};
  }
`

export const AvatarBtnIcon = styled.div`
  font-size: ${props => props.iconSize ? props.iconSize : '23px'};
  height: ${props => props.iconSize ? props.iconSize : '23px'};
  color: ${props => props.color ? props.color : '#000'};
  display: flex;
  align-items: center;
  justify-content: center;
`

export const AvatarBtnText = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  padding: ${props => props.padding ? props.padding : '0px 5px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '700'};
  color: ${props => props.color ? props.color : '#000'};
`

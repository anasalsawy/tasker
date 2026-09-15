import styled from 'styled-components';

export const Avatar = styled.div`
  width: ${props => (props.size) ? (''  + props.size + 'px') : '50px'};
  height: ${props => (props.size) ? (''  + props.size + 'px') : '50px'};
  border-radius: 50%;
  background: ${props => (props.color) ? props.color : 'var(--primary-color)'};
  color: ${props => (props.light) ? '#000' : '#fff'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: ${props => (props.size) ? (''  + (props.size / 2.2) + 'px') : '20px'};
  box-shadow: ${props => props.raised ? '0 4pt 8pt rgb(0 0 0 / 20%)' : 'none'};
  user-select: none;
`

export const AvatarImg = styled.img`
  width: 100%;
  height: 100%;
  background: transparent;
  border-radius: 50%;
  object-fit: cover;
  -o-object-fit: cover;
  object-position: center;
  -moz-user-select: none;
  -webkit-user-select: none;
  user-select: none;
  pointer-events: none;
`

export const Divider = styled.div`
  height: 0.8px;
  background: ${props => props.color ? props.color : 'rgba(0, 0, 0, 0.2)'};
`

export const FlexSpacer = styled.div`
  margin-left: ${props => props.isRTL ? '0px' : 'auto'};
  margin-right: ${props => props.isRTL ? 'auto' : '0px'};
`

export const Badge = styled.div`
  height: ${props => (props.size) ? (''  + props.size + 'px') : '30px'};
  width: ${props => (props.size) ? (''  + props.size + 'px') : '30px'};
  border-radius: 50%;
  color: #fff;
  background: ${props => (props.color) ? props.color : 'var(--danger-color)'};
  font-size: ${props => (props.size) ? (''  + (props.size / 2.2) + 'px') : '20px'};
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
`

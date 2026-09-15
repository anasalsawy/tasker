import styled from 'styled-components';
import { NavLink as LinkRR } from 'react-router-dom';

export const List = styled.div`
  display: flex;
  flex-direction: column;
  padding: ${props => props.padding ? props.padding : '0px'};
`

export const ListItem = styled.div`
  display: flex;
  align-items: center;
  cursor: ${props => props.clickable ? 'pointer' : 'auto'};
  color: var(--primary-color);
  text-decoration: none;
  padding: ${props => props.padding ? props.padding : '15px'};
  border-radius: ${props => props.borderRadius ? props.borderRadius : '0px'};
  background: ${props => (props.active && !props.disableHover) ? (props.isDarkMode ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)') : 'unset'};
  user-select: none;

  &:hover {
    background: ${props => !props.disableHover ? (props.isDarkMode ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)') : 'unset'};
  }
`

export const ListItemRR = styled(LinkRR)`
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--primary-color);
  text-decoration: none;
  padding: ${props => props.padding ? props.padding : '15px'};
  border-radius: ${props => props.borderRadius ? props.borderRadius : '0px'};
  user-select: none;

  &:hover {
    background: ${props => props.isDarkMode ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'};
  }

  &.active {
    background: ${props => props.isDarkMode ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'};
  }
`

export const ListItemIcon = styled.div`
  font-size: ${props => props.iconSize ? props.iconSize : '23px'};
  height: ${props => props.iconSize ? props.iconSize : '23px'};
  color: ${props => props.color ? props.color : '#000'};
  display: flex;
  align-items: center;
  justify-content: center;
`

export const ListItemImg = styled.img`
  width: ${props => props.size ? props.size : '50px'};
  height: ${props => props.size ? props.size : '50px'};
  object-fit: cover;
  -o-object-fit: cover;
  object-position: center;
  background: #fff;
  -moz-user-select: none;
  -webkit-user-select: none;
  user-select: none;
  pointer-events: none;
`

export const ListItemContent = styled.div`
  display: flex;
  flex-direction: column;
  padding: 0px 15px;
`

export const ListItemTitle = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '16px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '600'};
  color: ${props => props.color ? props.color : '#000'};
`

export const ListItemSubtitle = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '14px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '400'};
  color: ${props => props.color ? props.color : 'rgba(0, 0, 0, 0.5)'};
`

export const ListItemThirdTxt = styled.div`
  font-size: ${props => props.fontSize ? props.fontSize : '14px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '400'};
  color: ${props => props.color ? props.color : 'rgba(0, 0, 0, 0.5)'};
`

export const ListItemEnd = styled.div`
  margin-left: ${props => props.isRTL ? '0' : 'auto'};
  margin-right: ${props => props.isRTL ? 'auto' : '0'};
`

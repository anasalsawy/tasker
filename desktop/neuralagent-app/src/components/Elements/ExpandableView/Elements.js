import styled from 'styled-components';

export const ExpandableViewContainer = styled.div`
  background: ${props => props.color ? props.color : 'transparent'};
`

export const ExpandableViewDiv = styled.div`
  display: flex;
  align-items: center;
  padding: ${props => props.padding ? props.padding : '15px 10px'};
  cursor: pointer;
  user-select: none;
`

export const ActionsContainer = styled.div`
  margin-left: ${props => props.isRTL ? '0px' : 'auto'};
  margin-right: ${props => props.isRTL ? 'auto' : '0px'};
  display: flex;
  align-items: center;
`

export const Action = styled.div`
  padding: 0px 3px;
`

export const ArrowIcon = styled.div`
  font-size: 23px;
  height: 23px;
  padding: 0px 3px;
  color: ${props => props.color ? props.color : '#000'};
`

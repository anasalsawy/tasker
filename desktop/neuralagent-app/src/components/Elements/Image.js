import styled from 'styled-components';

export const Image = styled.img`
  width: ${props => props.width ? props.width : '100%'};
  height: ${props => props.height ? props.height : '300px'};
  object-fit: ${props => props.contain ? 'contain' : 'cover'};
  object-position: center;
  pointer-events: none;
  user-select: none;
`

export const ZoomImageContainer = styled.div`
  overflow: hidden;
`

export const ZoomImage = styled.img`
  width: ${props => props.width ? props.width : '100%'};
  height: ${props => props.height ? props.height : '300px'};
  object-fit: ${props => props.contain ? 'contain' : 'cover'};
  cursor: ${props => props.clickable ? 'pointer' : 'auto'};
  transition: all 0.3s ease 0s;
  object-position: center;
  user-select: none;

  &:hover {
    transform: scale(1.25);
  }
`

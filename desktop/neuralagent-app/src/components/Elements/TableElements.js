import styled from "styled-components";

export const Table = styled.table`
  border-collapse: collapse; 
  background-color: #f6f6f6;
  width: 100%;
  table-layout: fixed;
`

export const TH = styled.th`
  border: 1px solid #999;
  padding: 10px;
  background: ${props => props.background ? props.background : 'var(--primary-color)'};
  color: white;
  border-radius: 0;
  text-align: center;
  font-size: 16px;
  font-weight: 400;
`

export const TR = styled.tr`
  cursor: ${[props => props.clickable ? 'pointer' : 'auto']};
  
  &:hover {
    background: ${[props => props.clickable ? 'rgba(0, 0, 0, 0.04)' : 'transparent']};
  }
`

export const TD = styled.td`
  border: 1px solid #999;
  padding: 10px;
  font-size: ${props => props.fontSize ? props.fontSize : '14px'};
  font-weight: ${props => props.fontWeight ? props.fontWeight : '400'};
  background: ${props => props.background ? props.background : 'transparent'};
  color: ${props => props.color ? props.color : '#000'};
  word-wrap: break-word
`

export const TBody = styled.tbody`
  background-color: #fff;
`

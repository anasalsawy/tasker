import styled from 'styled-components';

export const ViewerCard = styled.div`
  background: #fff;
  width: 100%;
  position: relative;
  box-shadow: rgba(0, 0, 0, 0.16) 0px 1px 4px;
  min-height: 90vh;
  padding-bottom: 15px;
  border-radius: 5px;
`

export const BackBtnContainer = styled.div`
  position: absolute;
  top: 10px;
  right: ${props => props.isRTL ? '10px' : 'unset'};
  left: ${props => props.isRTL ? 'unset' : '10px'};
`

export const ActionsContainer = styled.div`
  position: absolute;
  top: 10px;
  left: 15px;
  display: flex;
  align-items: center;
`

export const ValueDiv = styled.div`
  border: thin solid rgba(0,0,0,0.12);
  padding: 15px 30px;
  background: rgba(0, 0, 0, 0.02);
`

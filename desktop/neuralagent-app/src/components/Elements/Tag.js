import styled from 'styled-components';

export const Tag = styled.div`
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 13px;
  font-weight: 500;
  background-color: ${props => props.color ? props.color : 'var(--primary-color)'};
  color: #fff;
  border-radius: 50px;
  gap: 6px;
  user-select: none;
`;

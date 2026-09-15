import styled from 'styled-components';
import { NavLink } from 'react-router-dom';

export const SidebarContainer = styled.div`
  width: 260px;
  display: flex;
  flex-direction: column;
  padding: 12px;
  border-right: thin solid rgba(255, 255, 255, 0.3);
`;

export const LogoWrapper = styled(NavLink)`
  display: flex;
  justify-content: center;
  margin-top: 8px;
  margin-bottom: 15px;
`;

export const Logo = styled.img`
  object-fit: contain;
  pointer-events: none;
  user-select: none;
`;

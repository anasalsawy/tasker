import styled from 'styled-components';

export const MainContainer = styled.div`
  width: 100%;
  background: var(--primary-color);
`

export const AccountContainer = styled.div`
  min-height: 100vh;
  padding: 15px;
  max-width: var(--max-login-width);
  margin-left: auto;
  margin-right: auto;
`

export const AccountHeader = styled.div`
  display: flex;
  align-items: center;
  margin-top: 20px;
`

export const AccountDiv = styled.div`
  min-height: 80vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
`

export const InfoContainer = styled.div`
  width: 100%;
  max-width: 500px;
  margin-left: auto;
  margin-right: auto;
  color: #fff;
  display: flex;
  flex-direction: column;
`

export const FormTitle = styled.div`
  font-size: 40px;
  text-align: center;
  font-weight: 300;
`

export const AccountTextField = styled.input`
  background: #fff;
  width: 100%;
  padding: 16px 20px;
  color: #000;
  font-size: 18px;
  margin-bottom: 20px;
  border-radius: 10px;
  font-family: inherit;
  transition: 0.1s ease;
  resize: none;
  outline: none;
  border: none;

  &::placeholder {
    color: rgba(0, 0, 0, 0.6);
    font-size: 18px;
    font-weight: 500;
    user-select: none;
  }
`

export const OrDiv = styled.div`
  display: flex;
  align-items: center;
  text-align: center;

  &::before, &::after {
  content: '';
  flex: 1;
  border-bottom: 2px solid #fff;
  margin: 0 10px;
}
`

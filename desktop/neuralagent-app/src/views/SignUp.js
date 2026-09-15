import React, { useEffect, useState } from 'react';
import {
  MainContainer,
  AccountContainer,
  AccountDiv,
  AccountHeader,
  InfoContainer,
  FormTitle,
  AccountTextField,
  OrDiv
} from '../components/OuterElements';
import neuralagent_logo_white from '../assets/neuralagent_logo_white.png';
import { Button, BtnIcon } from '../components/Elements/Button';
import { EMAIL_REGEX } from '../utils/regex';
import { useDispatch } from 'react-redux';
import { setLoadingDialog, setError } from '../store';
import constants from '../utils/constants';
import { useNavigate } from 'react-router-dom';
import axios, { API_KEY_HEADER } from '../utils/axios';
import { Text } from '../components/Elements/Typography';
import { FcGoogle } from "react-icons/fc";
import { FlexSpacer } from '../components/Elements/SmallElements';


function SignUp() {

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPasssord, setConfirmPassword] = useState('');

  const dispatch = useDispatch();
  const navigate = useNavigate();
  
  const isFormValid = () => {
    let isValid = firstName.length > 0 && lastName.length > 0 && email.length > 0 && password.length > 0;
    isValid = isValid && EMAIL_REGEX.test(email);
    isValid = isValid && password === confirmPasssord;
    return isValid;
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      signUp();
    }
  }

  const signUp = () => {
    if (!isFormValid()) {
      return;
    }

    const data = {
      name: firstName + ' ' + lastName,
      email: email,
      password: password,
    }

    dispatch(setLoadingDialog(true));
    axios.post('/auth/signup', data, API_KEY_HEADER).then((response) => {
      dispatch(setLoadingDialog(false));
      window.electronAPI.setToken(response.data.token);
      window.electronAPI.setRefreshToken(response.data.refresh_token);
      window.location.reload();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      dispatch(setError(true, constants.GENERAL_ERROR));
      setTimeout(() => {
        dispatch(setError(false, ''));
      }, 3000);
    });
  }

  const loginWithGoogle = async () => {
    try {
      const { code, codeVerifier } = await window.electronAPI.loginWithGoogle();
  
      const response = await axios.post('/auth/login_google_desktop', {
        code,
        code_verifier: codeVerifier,
      });
  
      const { token, refresh_token } = response.data;
  
      window.electronAPI.setToken(token);
      window.electronAPI.setRefreshToken(refresh_token);
  
      window.location.reload();
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  return (
    <>
      <MainContainer>
        <AccountContainer>
          <AccountHeader>
            <a href={constants.NEURALAGENT_LINK} target="_blank" rel="noreferrer" style={{textDecoration: 'none'}}>
              <img
                src={neuralagent_logo_white}
                height={45}
                alt="NeuralAgent"
                style={{userSelect: 'none', pointerEvents: 'none'}}
              />
            </a>
            <FlexSpacer isRTL={false} />
            <Button color="#fff"
              padding="14px 20px"
              onClick={() => navigate('/login')}
              borderRadius={20}>
              Login
            </Button>
          </AccountHeader>
          <AccountDiv>
            <InfoContainer>
              <FormTitle style={{textAlign: 'center'}}>
                Sign Up
              </FormTitle>
              <AccountTextField placeholder={'First Name'} style={{marginTop: '30px'}} type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <AccountTextField placeholder={'Last Name'} style={{marginTop: '5px'}} type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <AccountTextField placeholder={'Email'} style={{marginTop: '5px'}} type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <AccountTextField placeholder={'Password'} style={{marginTop: '5px'}} type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <AccountTextField placeholder={'Confirm Password'} style={{marginTop: '5px'}} type="password"
                value={confirmPasssord}
                onChange={(e) => setConfirmPassword(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <Button color="var(--third-color)" padding="14px" fontSize="18px" borderRadius={20}
                block
                dark
                disabled={!isFormValid()}
                onClick={() => signUp()}>
                Confirm
              </Button>
              <div style={{marginTop: '10px', textAlign: 'center'}}>
                <OrDiv>
                  <Text fontSize="18px" color="#fff">
                    OR
                  </Text>
                </OrDiv>
                <Button color="#fff" padding="10px 14px" fontSize="16px" borderRadius={10}
                  block
                  style={{marginTop: '10px'}}
                  onClick={() => loginWithGoogle()}>
                  <BtnIcon iconSize='22px' left>
                    <FcGoogle />
                  </BtnIcon>
                  Continue With Google
                </Button>
              </div>
            </InfoContainer>
          </AccountDiv>
        </AccountContainer>
      </MainContainer>
    </>
  );
}

export default SignUp;
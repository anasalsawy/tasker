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
import { Button, AvatarButton, AvatarBtnIcon, BtnIcon } from '../components/Elements/Button';
import { EMAIL_REGEX } from '../utils/regex';
import { useDispatch } from 'react-redux';
import { setLoadingDialog, setError } from '../store';
import constants from '../utils/constants';
import { useNavigate, Link } from 'react-router-dom';
import axios, { API_KEY_HEADER } from '../utils/axios';
import { Text } from '../components/Elements/Typography';
import { FaFacebookF } from "react-icons/fa";
import { FcGoogle } from "react-icons/fc";
import { FlexSpacer } from '../components/Elements/SmallElements';


function Login() {

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const dispatch = useDispatch();
  const navigate = useNavigate();
  
  const isFormValid = () => {
    let isValid = email.length > 0 && password.length > 0;
    isValid = isValid && EMAIL_REGEX.test(email);
    return isValid;
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      loginUser();
    }
  }

  const setTitle = () => {
    document.title = 'Login | ' + constants.APP_NAME;
  }

  const loginUser = () => {
    if (!isFormValid()) {
      return;
    }
    dispatch(setLoadingDialog(true));
    axios.post('/auth/login', {email: email, password: password}, API_KEY_HEADER).then((response) => {
      dispatch(setLoadingDialog(false));
      window.electronAPI.setToken(response.data.token);
      window.electronAPI.setRefreshToken(response.data.refresh_token);
      window.location.reload();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.UNAUTHORIZED) {
        dispatch(setError(true, 'Incorrect Email or Password, Please try again.'));
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
      }
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
  
  useEffect(() => {
    setTitle();
  }, []);

  return (
    <>
      <MainContainer>
        <AccountContainer>
          <AccountHeader>
            <img
              src={neuralagent_logo_white}
              height={45}
              alt="NeuralAgent"
              style={{userSelect: 'none', pointerEvents: 'none'}}
            />
            <FlexSpacer isRTL={false} />
            <Button color="#fff"
              padding="14px 20px"
              onClick={() => navigate('/signup')}
              borderRadius={20}>
              Sign Up
            </Button>
          </AccountHeader>
          <AccountDiv>
            <InfoContainer>
              <FormTitle style={{textAlign: 'center'}}>
                Login to NeuralAgent
              </FormTitle>
              <AccountTextField placeholder={'Email'} style={{marginTop: '30px'}} type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <AccountTextField placeholder={'Password'} style={{marginTop: '10px'}} type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e)} />
              <Button color="var(--third-color)" padding="14px" fontSize="18px" borderRadius={20}
                block
                dark
                disabled={!isFormValid()}
                onClick={() => loginUser()}>
                Login
              </Button>
              <FlexSpacer isRTL={false} style={{marginTop: '10px'}}>
                <Link to="/forgot-password" style={{color: 'white'}}>
                  Forgot Password?
                </Link>
              </FlexSpacer>
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

export default Login;
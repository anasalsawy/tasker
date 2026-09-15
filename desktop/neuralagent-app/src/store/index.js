import { configureStore } from '@reduxjs/toolkit';

export function setAppLoading(isLoading) {
  return {
    type: 'SET_APP_LOADING',
    isAppLoading: isLoading,
  };
}

export function setFullLoading(isLoading) {
  return {
    type: 'SET_FULL_LOADING',
    isFullLoading: isLoading,
  };
}

export function setLoadingDialog(isLoading) {
  return {
    type: 'SET_LOADING_DIALOG',
    isLoadingDialog: isLoading,
  };
}

export function setAccessToken(accessToken) {
  return {
    type: 'SET_ACCESS_TOKEN',
    accessToken: accessToken,
  };
}

export function setUser(user) {
  return {
    type: 'SET_USER',
    user: user,
  };
}

export function setError(isError, errorMessage='') {
  return {
    type: 'SET_ERROR',
    isError: isError,
    errorMessage: errorMessage,
  };
}

export function setSuccess(isSuccess, successMsg='') {
  return {
    type: 'SET_SUCCESS',
    isSuccess: isSuccess,
    successMsg: successMsg,
  };
}

const defaultState = {
  isAppLoading: true,
  isFullLoading: false,
  isLoadingDialog: false,
  accessToken: null,
  user: null,
  isError: false,
  errorMessage: '',
  isSuccess: false,
  successMsg: '',
}

function reducer(state=defaultState, action) {
  let newState = Object.assign({}, state);
  switch (action.type) {
    case 'SET_APP_LOADING':
      newState.isAppLoading = action.isAppLoading;
      return newState;
    case 'SET_FULL_LOADING':
      newState.isFullLoading = action.isFullLoading;
      return newState;
    case 'SET_LOADING_DIALOG':
      newState.isLoadingDialog = action.isLoadingDialog;
      return newState;
    case 'SET_ACCESS_TOKEN':
      newState.accessToken = action.accessToken;
      return newState;
    case 'SET_USER':
      newState.user = action.user;
      return newState;
    case 'SET_ERROR':
      if (action.isError) {
        newState.errorMessage = action.errorMessage;
      }
      newState.isError = action.isError;
      return newState;
    case 'SET_SUCCESS':
      if (action.isSuccess) {
        newState.successMsg = action.successMsg;
      }
      newState.isSuccess = action.isSuccess;
      return newState;
    default:
      break;
  }
  return state;
}

export const store = configureStore({ reducer: reducer });

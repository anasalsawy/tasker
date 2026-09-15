import constants from './constants';
import moment from 'moment';
// import 'moment/locale/ar';
import axios, { API_KEY_HEADER } from './axios';
import { setLoadingDialog } from '../store';


export function openInNewTab(url) {
  var win = window.open(url, '_blank')
  win.focus()
}

export const logoutUserLocally = (removeCookie) => {
  window.electronAPI.deleteToken();
  window.electronAPI.deleteRefreshToken();
  window.location.reload();
};

export const logoutUser = (accessToken, dispatch) => {
  console.log(accessToken);
  dispatch(setLoadingDialog(true));
  axios.post('/auth/logout', {access_token: accessToken}, API_KEY_HEADER)
    .then((response) => {
      dispatch(setLoadingDialog(false));
      logoutUserLocally();
    })
    .catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.UNAUTHORIZED) {
        logoutUserLocally();
      }
    });
}

export const refreshToken = async () => {
  axios.post('/auth/refresh_token', {
    refresh_token: await window.electronAPI.getRefreshToken(),
  }, API_KEY_HEADER).then((response) => {
    const data = response.data;
    window.electronAPI.setToken(data.new_token);
    if (data.new_refresh !== null) {
      window.electronAPI.setRefreshToken(data.new_refresh);
    }
    window.location.reload();
  }).catch((error) => {
    if (error.response.status === constants.status.UNAUTHORIZED) {
      logoutUserLocally();
    }
  });
};

export const getBadRequestErrorMessage = (data) => {

  if (data === null || data.message === undefined) {
    return constants.GENERAL_ERROR;
  }

  if (data.message === 'Limited_2_Projects') {
    return 'You are currently limited to two projects';
  }

  return constants.GENERAL_ERROR;
};

export const formatDateTime = (date_str, lang = 'en', format = 'LLLL') => {
  moment.locale(lang);
  let date = moment(date_str);
  return date.format(format);
};

export const localDateTimeToUtc = (time) => {
  moment.locale('en');
  let date = new moment(time, 'YYYY-MM-DDTHH:mm').utc();
  return date.format('YYYY-MM-DDTHH:mm');
};

export const utcDateTimeToLocal = (time) => {
  moment.locale('en');
  let date = moment.utc(time, 'YYYY-MM-DDTHH:mm').local();
  return date.format('YYYY-MM-DDTHH:mm');
};

export const formatTime = (time, format, lang = 'en') => {
  moment.locale(lang);
  let date = moment(time, 'HH:mm:ss');
  return date.format(format);
};

export const formatDate = (date_str, format) => {
  moment.locale('en');
  let date = moment(date_str);
  return date.format(format);
};

export const localTimeToUtc = (time) => {
  moment.locale('en');
  let date = new moment(time, 'HH:mm:ss').utc();
  return date.format('HH:mm:ss');
};

export const utcToLocalTime = (time) => {
  moment.locale('en');
  let date = moment.utc(time, 'HH:mm:ss').local();
  return date.format('HH:mm:ss');
};

export const isLessThanNow = (date) => {
  let current_time = moment();
  let shown_at = moment(utcDateTimeToLocal(date));
  let dif = current_time.diff(shown_at);
  return dif > 0;
};

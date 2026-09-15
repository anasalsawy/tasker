import React, { useState, useEffect } from 'react';
import './App.css';
import {
  HashRouter as Router, // BrowserRouter
  Routes,
  Route
} from "react-router-dom";
import { useSelector, useDispatch } from 'react-redux';
import LoadingDialog from './components/LoadingDialog';
import FullLoading from './components/FullLoading';
import constants from './utils/constants';
import MessageBar from './components/Elements/MessageBar';
import { setAppLoading, setUser, setAccessToken, setLoadingDialog } from './store';
import RedirectTo from './components/RedirectTo';
import axios from './utils/axios';
import { logoutUser, refreshToken } from './utils/helpers';
import { AppMainContainer, OverlayContainer } from './layouts/Containers';
import Sidebar from './layouts/Sidebar';
import { useLocation } from 'react-router-dom';

import Login from './views/Login';
import SignUp from './views/SignUp';
import Home from './views/Home';
import Thread from './views/Thread';
import Overlay from './views/Overlay';
import BackgroundAuth from './views/BackgroundAuth';
import BackgroundTask from './views/BackgroundTask';
import BackgroundSetup from './views/BackgroundSetup';

function AppRoutes() {
  const location = useLocation();
  const isOverlayRoute = location.pathname === '/overlay';
  const isBackgroundModeRoutes = location.pathname === '/background-auth' || location.pathname === '/background-task' || location.pathname === '/background-setup';

  const accessToken = useSelector(state => state.accessToken);
  const isError = useSelector(state => state.isError);
  const errorMessage = useSelector(state => state.errorMessage);
  const isSuccess = useSelector(state => state.isSuccess);
  const successMsg = useSelector(state => state.successMsg);

  return (
    <>
      {isError && <MessageBar message={errorMessage} backgroundColor='var(--danger-color)' />}
      {isSuccess && <MessageBar message={successMsg} backgroundColor='var(--success-color)' />}

      {accessToken !== null ? (
        isOverlayRoute || isBackgroundModeRoutes ? (
          isOverlayRoute ? (
            <OverlayContainer>
              <Routes>
                <Route path="/overlay" element={<Overlay />} />
              </Routes>
            </OverlayContainer>
          ) : (
            <Routes>
              <Route path="/background-auth" element={<BackgroundAuth />} />
              <Route path="/background-task" element={<BackgroundTask />} />
              <Route path="/background-setup" element={<BackgroundSetup />} />
            </Routes>
          )
        ) : (
          <AppMainContainer>
            <Sidebar />
            <Routes>
              <Route path='/' element={<Home />} />
              <Route path='/threads/:tid' element={<Thread />} />
              <Route path="*" element={<RedirectTo linkType="router" to="/" redirectType="replace" />} />
            </Routes>
          </AppMainContainer>
        )
      ) : (
        <Routes>
          <Route path="login" element={<Login />} />
          <Route path="signup" element={<SignUp />} />
          <Route path="*" element={<RedirectTo linkType="router" to="/login" redirectType="replace" />} />
        </Routes>
      )}
    </>
  );
}


function App() {

  const isAppLoading = useSelector(state => state.isAppLoading);
  const isFullLoading = useSelector(state => state.isFullLoading);
  const isLoadingDialog = useSelector(state => state.isLoadingDialog);

  const dispatch = useDispatch();
  const [_windowDims, setWindowDims] = useState();

  const [isMobileBarOpen, setMobileBarOpen] = useState(false);

  const handleResize = () => {
    setWindowDims({
      height: window.innerHeight,
      width: window.innerWidth
    });
  }

  useEffect(() => {
    window.addEventListener('resize', handleResize);

    return () => {
        window.removeEventListener('resize', handleResize);
    };
  }, []);

  useEffect(() => {
    const asyncTask = async () => {
      const storedAccessToken = await window.electronAPI.getToken();
      console.log(storedAccessToken);
      if (storedAccessToken !== undefined && storedAccessToken !== null) {
        dispatch(setAccessToken(storedAccessToken));
        getUserInfo(storedAccessToken);
      } else {
        dispatch(setAppLoading(false));
      }
    }
    asyncTask();
  }, []);

  const getUserInfo = (accessToken) => {
    dispatch(setAppLoading(true));
    axios.get('/auth/user_info', {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      dispatch(setUser(response.data));
      dispatch(setAppLoading(false));
    }).catch((error) => {
      if (error.response.status === constants.status.UNAUTHORIZED) {
        refreshToken();
      } else {
        dispatch(setAppLoading(false));
      }
    });
  };

  useEffect(() => {
    if (window.electronAPI?.onLogout) {
      window.electronAPI.onLogout(async () => {
        const token = await window.electronAPI.getToken();
        logoutUser(token, dispatch);
      });
    }
  }, []);

  const cancelAllRunningTasks = async () => {
    const token = await window.electronAPI.getToken();
    if (token === null) {
      return;
    }
    dispatch(setLoadingDialog(true));
    try {
      await axios.post(`/threads/cancel_all_running_tasks`, {}, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      window.electronAPI.stopAIAgent();
    } catch (error) {
    } finally {
      dispatch(setLoadingDialog(false));
    }
  };

  useEffect(() => {
    if (window.electronAPI?.onCancelAllTasksTrigger) {
      window.electronAPI.onCancelAllTasksTrigger(async () => {
        await cancelAllRunningTasks();
        window.electronAPI.cancelAllTasksDone();
      });
    }
  }, []);

  return (
    <>
      {
        isFullLoading ? <FullLoading /> : <></>
      }
      {
        isLoadingDialog ? <LoadingDialog /> : <></>
      }
      {
        isAppLoading ? <FullLoading /> :
        <Router>
          <AppRoutes />
        </Router>
      }
    </>
  );
}


export default App;
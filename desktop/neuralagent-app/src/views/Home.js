import React, { useState, useEffect } from 'react';
import { FlexSpacer } from '../components/Elements/SmallElements';
import { IconButton } from '../components/Elements/Button';
import { FaArrowAltCircleUp } from 'react-icons/fa';
import { useDispatch, useSelector } from 'react-redux';
import axios from '../utils/axios';
import { setLoadingDialog, setError } from '../store';
import constants from '../utils/constants';
import { Text } from '../components/Elements/Typography';
import NATextArea from '../components/Elements/TextAreas';
import { useNavigate } from 'react-router-dom';
import { MdOutlineSchedule } from 'react-icons/md';
import { GiBrain } from 'react-icons/gi';

import styled from 'styled-components';

const HomeDiv = styled.div`
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
`;

const Card = styled.div`
  border: thin solid rgba(255,255,255,0.3);
  border-radius: 20px;
  padding: 15px;
  width: 100%;
  max-width: 600px;
`;

const ToggleContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  color: var(--secondary-color);
`;

const ModeToggle = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  background-color: ${({ active }) => (active ? 'rgba(255,255,255,0.1)' : 'transparent')};
  color: #fff;
  border: thin solid rgba(255,255,255,0.3);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 13px;
  transition: background-color 0.2s ease;
  cursor: pointer;

  &:hover {
    background-color: rgba(255,255,255,0.1);
  }
`;


export default function Home() {
  const [messageText, setMessageText] = useState('');
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);

  const accessToken = useSelector(state => state.accessToken);

  const dispatch = useDispatch();

  const navigate = useNavigate();

  const cancelRunningTask = (tid) => {
    dispatch(setLoadingDialog(true));
    axios.post(`/threads/${tid}/cancel_task`, {}, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      dispatch(setLoadingDialog(false));
      window.electronAPI.stopAIAgent();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.BAD_REQUEST) {
        dispatch(setError(true, constants.GENERAL_ERROR));
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
      }
      setTimeout(() => {
        dispatch(setError(false, ''));
      }, 3000);
    });
  };

  const createThread = async () => {
    if (messageText.length === 0) {
      return;
    }
    const data = {task: messageText, background_mode: backgroundMode, extended_thinking_mode: thinkingMode};
    setMessageText('');
    dispatch(setLoadingDialog(true));
    axios.post('/threads', data, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then(async (response) => {
      dispatch(setLoadingDialog(false));
      if (response.data.type === 'desktop_task') {
        if (!backgroundMode && response.data.is_background_mode_requested) {
          const ready = await window.electronAPI.isBackgroundModeReady();
          if (!ready) {
            cancelRunningTask();
            return;
          }
        }
        setBackgroundMode(backgroundMode || response.data.is_background_mode_requested);
        setThinkingMode(thinkingMode || response.data.is_extended_thinking_mode_requested);
        window.electronAPI.setLastThinkingModeValue((thinkingMode || response.data.is_extended_thinking_mode_requested).toString());
        window.electronAPI.launchAIAgent(
          process.env.REACT_APP_PROTOCOL + '://' + process.env.REACT_APP_DNS,
          response.data.thread_id,
          backgroundMode || response.data.is_background_mode_requested
        );
      }
      navigate('/threads/' + response.data.thread_id);
      window.location.reload();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.BAD_REQUEST) {
        if (error.response.data?.message === 'Not_Browser_Task_BG_Mode') {
          dispatch(setError(true, 'Background Mode only supports browser tasks.'));
        } else {
          dispatch(setError(true, constants.GENERAL_ERROR));
        }
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
      }
      setTimeout(() => {
        dispatch(setError(false, ''));
      }, 3000);
    });
  };

  const handleTextEnterKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      createThread();
    }
  };

  const onBGModeToggleChange = async (value) => {
    if (value) {
      const ready = await window.electronAPI.isBackgroundModeReady();
      if (!ready) {
        window.electronAPI.startBackgroundSetup();
        return;
      }
    }
    setBackgroundMode(value);
  };

  useEffect(() => {
    if (window.electronAPI?.onAIAgentLaunch) {
      window.electronAPI.onAIAgentLaunch((threadId) => {
        navigate('/threads/' + threadId)
        window.location.reload();
      });
    }
  }, []);

  useEffect(() => {
    if (window.electronAPI?.onAIAgentExit) {
      window.electronAPI.onAIAgentExit(() => {
        window.location.reload();
      });
    }
  }, []);

  useEffect(() => {
    const asyncTask = async () => {
      const lastBackgroundModeValue = await window.electronAPI.getLastBackgroundModeValue();
      setBackgroundMode(lastBackgroundModeValue === 'true');
    };
    asyncTask();
  }, []);

  useEffect(() => {
    const asyncTask = async () => {
      const lastThinkingModeValue = await window.electronAPI.getLastThinkingModeValue();
      setThinkingMode(lastThinkingModeValue === 'true');
    };
    asyncTask();
  }, []);

  return (
    <HomeDiv>
      <Text fontWeight='600' fontSize='23px' color='#fff'>
        Start a New Task
      </Text>
      <Card style={{marginTop: '15px'}}>
        <NATextArea
          background='transparent'
          isDarkMode
          padding='10px 4px'
          placeholder="What do you want NeuralAgent to do?"
          rows='3'
          value={messageText}
          onChange={(e) => setMessageText(e.target.value)}
          onKeyDown={handleTextEnterKey}
        />
        <div style={{marginTop: '10px', display: 'flex', alignItems: 'center'}}>
          <ToggleContainer>
            <ModeToggle
              active={backgroundMode}
              onClick={() => onBGModeToggleChange(!backgroundMode)}
            >
              <MdOutlineSchedule style={{fontSize: '19px'}} />
              Background
            </ModeToggle>
          </ToggleContainer>
          <div style={{width: '10px'}} />
          <ToggleContainer>
            <ModeToggle
              active={thinkingMode}
              onClick={() => setThinkingMode(!thinkingMode)}
            >
              <GiBrain style={{fontSize: '19px'}} />
              Thinking
            </ModeToggle>
          </ToggleContainer>
          <FlexSpacer isRTL={false} />
          <IconButton
            iconSize='35px'
            color='#fff'
            disabled={messageText.length === 0}
            onClick={() => createThread()}
            onKeyDown={handleTextEnterKey}>
            <FaArrowAltCircleUp />
          </IconButton>
        </div>
      </Card>
    </HomeDiv>
  );
}

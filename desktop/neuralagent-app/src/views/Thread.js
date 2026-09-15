import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import axios from '../utils/axios';
import constants from '../utils/constants';
import { setLoadingDialog, setError } from '../store';
import ChatMessage from '../components/ChatMessage';
import { FlexSpacer } from '../components/Elements/SmallElements';
import NATextArea from '../components/Elements/TextAreas';
import { IconButton } from '../components/Elements/Button';
import { MdEdit, MdDelete } from 'react-icons/md';
import { FaArrowAltCircleUp, FaStopCircle } from 'react-icons/fa';
import ClipLoader from 'react-spinners/ClipLoader';
import { Text } from '../components/Elements/Typography';
import ThreadDialog from '../components/DataDialogs/ThreadDialog';
import YesNoDialog from '../components/Elements/YesNoDialog';
import { useNavigate } from 'react-router-dom';
import { MdOutlineSchedule } from 'react-icons/md';
import { GiBrain } from 'react-icons/gi';

import styled from 'styled-components';

const ThreadDiv = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const ChatContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  padding-top: 12px;
  padding-bottom: 12px;
`;

const SendingContainer = styled.div`
  border: thin solid rgba(255,255,255,0.3);
  padding: 10px;
  border-radius: 20px;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  padding: 20px;
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

export default function Thread() {
  
  const [thread, setThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState('');
  const [isSendingMessage, setSendingMessage] = useState(false);
  const [backgroundMode, setBackgroundMode] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);

  const [isThreadDialogOpen, setThreadDialogOpen] = useState(false);
  const [isDeleteThreadDialogOpen, setDeleteThreadDialogOpen] = useState(false);

  const accessToken = useSelector(state => state.accessToken);

  const { tid } = useParams();

  const bottomRef = useRef(null);

  const navigate = useNavigate();

  const dispatch = useDispatch();

  const getThread = () => {
    dispatch(setLoadingDialog(true));
    axios.get(`/threads/${tid}`, {
      headers: { 'Authorization': 'Bearer ' + accessToken }
    }).then(response => {
      setThread(response.data);
      dispatch(setLoadingDialog(false));
    }).catch(error => {
      dispatch(setLoadingDialog(false));
      if (error.response?.status === constants.status.UNAUTHORIZED) {
        window.location.reload();
      }
    });
  };

  const getThreadMessages = () => {
    dispatch(setLoadingDialog(true));
    axios.get(`/threads/${tid}/thread_messages`, {
      headers: { 'Authorization': 'Bearer ' + accessToken }
    }).then(response => {
      setMessages(response.data);
      dispatch(setLoadingDialog(false));
    }).catch(error => {
      dispatch(setLoadingDialog(false));
      if (error.response?.status === constants.status.UNAUTHORIZED) {
        window.location.reload();
      }
    });
  };

  const sendMessage = () => {
    if (messageText.length === 0 || isSendingMessage || thread.status === 'working') {
      return;
    }
    
    const data = {text: messageText.trim(), background_mode: backgroundMode, extended_thinking_mode: thinkingMode};
    setMessageText('');
    setSendingMessage(true);
    dispatch(setLoadingDialog(true));
    axios.post(`/threads/${tid}/send_message`, data, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then(async (response) => {
      dispatch(setLoadingDialog(false));
      setSendingMessage(false);
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
          tid,
          backgroundMode || response.data.is_background_mode_requested
        );
      }
      // TODO Remove
      getThread();
      getThreadMessages();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      setSendingMessage(false);
      if (error.response.status === constants.status.BAD_REQUEST) {
        if (error.response.data?.message === 'Not_Browser_Task_BG_Mode') {
          dispatch(setError(true, 'Background Mode only supports browser tasks.'));
        } else {
          dispatch(setError(true, 'Something Wrong Happened, Please try again.'));
        }
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
      }
      setTimeout(() => {
        dispatch(setError(false, ''));
      }, 3000);
    });
  };

  const deleteThread = () => {
    dispatch(setLoadingDialog(true));
    axios.delete('/threads/' + tid, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      dispatch(setLoadingDialog(false));
      navigate('/');
      window.location.reload();
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.UNAUTHORIZED) {
        window.location.reload();
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
        setTimeout(() => {
          dispatch(setError(false, ''));
        }, 3000);
      }
    });
  }

  const cancelRunningTask = () => {
    if (thread.status !== 'working') {
      return;
    }

    dispatch(setLoadingDialog(true));
    axios.post(`/threads/${tid}/cancel_task`, {}, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      dispatch(setLoadingDialog(false));
      window.electronAPI.stopAIAgent();
      // TODO Remove
      getThreadMessages();
      getThread();
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

  const handleTextEnterKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
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
    getThread();
    getThreadMessages();
  }, [tid]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (window.electronAPI?.onAIAgentLaunch) {
      window.electronAPI.onAIAgentLaunch(() => {
        window.location.reload();
      });
    }
  }, []);

  useEffect(() => {
    if (window.electronAPI?.onAIAgentExit) {
      window.electronAPI.onAIAgentExit(() => {
        getThread();
        getThreadMessages();
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

  return thread !== null ? (
    <>
      <ThreadDialog
        isOpen={isThreadDialogOpen}
        setOpen={setThreadDialogOpen}
        threadObj={Object.assign({}, thread)}
        onSuccess={() => window.location.reload()}
      />
      <YesNoDialog
        isOpen={isDeleteThreadDialogOpen}
        setOpen={setDeleteThreadDialogOpen}
        title='Delete Thread'
        text='Are you sure that you want to delete this thread?'
        onYesClicked={deleteThread}
        isDarkMode={true}
      />
      <ThreadDiv>
        <Header>
          <Text fontSize='20px' fontWeight='600' color={'#fff'}>
            {thread.title}
          </Text>
          <FlexSpacer />
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <IconButton iconSize='27px' color='#fff' style={{ margin: '0 5px' }} dark
              onClick={() => setThreadDialogOpen(true)}>
              <MdEdit />
            </IconButton>
            <IconButton iconSize='27px' color='#fff' style={{ margin: '0 5px' }} dark
              onClick={() => setDeleteThreadDialogOpen(true)}>
              <MdDelete />
            </IconButton>
          </div>
        </Header>
        <ChatContainer>
          {messages.map((msg) => (
            <ChatMessage key={'thread_message__' + msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </ChatContainer>
        <div style={{ padding: '15px' }}>
          <SendingContainer>
            <NATextArea
              background='transparent'
              placeholder={'What do you want NeuralAgent to do?'}
              value={messageText}
              isDarkMode
              rows='2'
              onKeyDown={handleTextEnterKey}
              onChange={(e) => setMessageText(e.target.value)}
            />
            <div style={{ marginTop: '5px', display: 'flex', alignItems: 'center' }}>
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
              <FlexSpacer />
              {isSendingMessage ? (
                <ClipLoader color={'#fff'} size={40} />
              ) : (
                thread.status === 'working' ? (
                  <IconButton
                    iconSize='35px'
                    color={'#fff'}
                    onClick={() => cancelRunningTask()}>
                    <FaStopCircle />
                  </IconButton>
                ) : (
                  <IconButton
                    iconSize='35px'
                    color={'#fff'}
                    disabled={messageText.length === 0}
                    onClick={() => sendMessage()}>
                    <FaArrowAltCircleUp />
                  </IconButton>
                )
              )}
            </div>
          </SendingContainer>
        </div>
      </ThreadDiv>
    </>
  ) : <></>;
}

import React, { useEffect, useState } from 'react';
import neuralagent_logo_white from '../../assets/neuralagent_logo_white.png';
import { BtnIcon, Button } from '../../components/Elements/Button';
import { MdAddCircleOutline } from 'react-icons/md';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { setLoadingDialog } from '../../store';
import constants from '../../utils/constants';
import axios from '../../utils/axios';
import {
  SidebarContainer,
  LogoWrapper,
  Logo
} from './SidebarElements';
import {
  List,
  ListItemRR,
  ListItemContent,
  ListItemTitle
} from '../../components/Elements/List';
import { Text } from '../../components/Elements/Typography';


export default function Sidebar() {

  const [threads, setThreads] = useState([]);

  const isLoading = useSelector(state => state.isLoading);
  const accessToken = useSelector(state => state.accessToken);

  const navigate = useNavigate();

  const dispatch = useDispatch();

  const getThreads = () => {
    dispatch(setLoadingDialog(true));
    axios.get('/threads', {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      setThreads(response.data);
      dispatch(setLoadingDialog(false));
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.UNAUTHORIZED) {
        window.location.reload();
      }
    });
  }

  useEffect(() => {
    getThreads();
  }, []);

  return (
    <SidebarContainer>
      <LogoWrapper to="/">
        <Logo
          src={neuralagent_logo_white}
          alt="NeuralAgent"
          height={40}
        />
      </LogoWrapper>
      <Button padding='7px 15px' color={'var(--primary-color)'} borderRadius={6} fontSize='15px' dark
         onClick={() => navigate('/')}>
        <BtnIcon left color='#fff' iconSize='23px'>
          <MdAddCircleOutline />
        </BtnIcon>
        New Task
      </Button>
      <List padding='0px 10px' style={{marginTop: '10px', overflowY: 'auto'}}>
        {
          !isLoading && threads.length === 0 ? (
            <Text style={{marginTop: '7px', padding: '8px'}}
              fontSize='14px'
              textAlign='center'
              color={'rgba(255,255,255,0.7)'}>
              You currently have no threads
            </Text>
          ) : (
            <>
              {threads.map((thread) => {
                return (
                  <ListItemRR key={'thread__' + thread.id} padding='10px' to={'/threads/' + thread.id} isDarkMode
                    borderRadius='8px'
                    style={{marginTop: '5px'}}>
                    <ListItemContent>
                      <ListItemTitle fontSize='14px' color='#fff' fontWeight='400'>
                        {thread.title}
                      </ListItemTitle>
                    </ListItemContent>
                  </ListItemRR>
                )
              })}
            </>
          )
        }
      </List>
    </SidebarContainer>
  );
}

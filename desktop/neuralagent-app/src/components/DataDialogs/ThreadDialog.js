import React, { useState, useEffect } from 'react';
import Dialog from '../Elements/Dialog';
import { setLoadingDialog, setSuccess, setError } from '../../store';
import { useDispatch, useSelector } from 'react-redux';
import axios from '../../utils/axios';
import constants from '../../utils/constants';
import { FlexSpacer } from '../Elements/SmallElements';
import { Button } from '../Elements/Button';
import NATextField from '../Elements/TextFields';
import { getBadRequestErrorMessage } from '../../utils/helpers';


function ThreadDialog({ isOpen, setOpen, threadObj=null, onSuccess }) {

  const [title, setTitle] = useState('');

  const accessToken = useSelector(state => state.accessToken);
  
  const dispatch = useDispatch();

  const clearData = () => {
    setTitle('');
  };

  const setDialogOpen = (open) => {
    if (!open) {
      clearData();
    }
    setOpen(open);
  };

  const isFormValid = () => {
    return title.length > 0;
  };

  const editThread = () => {
    if (!isFormValid()) {
      return;
    }

    let data = {
      title: title,
    };

    dispatch(setLoadingDialog(true));
    axios.put('/threads/' + threadObj.id, data, {
      headers: {
        'Authorization': 'Bearer ' + accessToken,
      }
    }).then((response) => {
      dispatch(setLoadingDialog(false));
      dispatch(setSuccess(true, 'Action Executed Successfully!'));
      setTimeout(() => {
        dispatch(setSuccess(false, ''));
      }, 3000);
      setDialogOpen(false);
      if (onSuccess !== null) {
        onSuccess();
      }
    }).catch((error) => {
      dispatch(setLoadingDialog(false));
      if (error.response.status === constants.status.BAD_REQUEST) {
        dispatch(setError(true, getBadRequestErrorMessage(error.response.data)));
      } else {
        dispatch(setError(true, constants.GENERAL_ERROR));
      }
      setTimeout(() => {
        dispatch(setError(false, ''));
      }, 3000);
    });
  };

  const onConfirmClick = () => {
    editThread();
  };

  useEffect(() => {
    if (threadObj !== null) {
      setTitle(threadObj.title);
    } else {
      clearData();
    }
  }, [threadObj]);

  return (
    <>
      <Dialog
        isOpen={isOpen}
        setOpen={setDialogOpen}
        maxWidth="500px"
        title={'Edit Thread'}
        padding='10px 15px'
        isDarkMode
        child={
          <>
            <div>
              <NATextField
                type="text"
                label='Title'
                labelFontWeight='500'
                verticalLabel
                value={title}
                background='rgba(0, 0, 0, 0.3)'
                isDarkMode
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
          </>
        }
        actions={
          <>
            <FlexSpacer />
            <Button borderRadius={7} padding="10px 15px" dark disabled={!isFormValid()}
              onClick={onConfirmClick}>
              Confirm
            </Button>
          </>
        }
      />
    </>
  );
}

export default ThreadDialog;
